"""
Detector de Estagnação e Controlador de Escalonamento FAST -> SMART do Harness.

Responsável por:
1. Distinguir falha de ferramenta, sucesso sem progresso, repetição de consultas e avanço real de estado;
2. Monitorar ciclos consecutivos de ferramentas sem avanço de estado/progresso da tarefa;
3. Tratar 'save_memory' isolado como NÃO sendo progresso real da tarefa;
4. Resetar o contador de estagnação mediante transições reais de estado;
5. Detectar estagnação de raciocínio de forma determinística;
6. Emitir o evento/estado estruturado ESCALATE_TO_SMART para diagnóstico.
"""

from dataclasses import dataclass, field
from typing import Any


# Rationale: 6 ações consecutivas bem-sucedidas sem nenhuma alteração de estado,
# edição de arquivo ou avanço de especificação/registry indicam que o modelo FAST
# já esgotou a fase de leitura exploratória e está estagnado em loop de raciocínio.
DEFAULT_MAX_STAGNATION_CYCLES = 6

# Rationale: Repetir a mesma consulta de inspeção 3 vezes consecutivas sem
# alteração intermediária de estado comprova ciclo vicioso de consultas.
DEFAULT_MAX_REPEATED_QUERIES = 3

# Limiares inspirados no StuckDetector do OpenHands:
# a mesma ação falhando 3 vezes seguidas, ou duas ações alternando por 6 ciclos.
STUCK_SAME_ERROR_REPEATS = 3
STUCK_ALTERNATING_CYCLES = 6

READ_ONLY_TOOLS = {
    "list_directory",
    "read_file",
    "check_tools",
    "load_skill",
    "get_project_status",
    "get_memory",
    "get_model_registry",
    "web_search",
    "fetch_url",
}

STATE_MUTATING_TOOLS = {
    "write_file",
    "replace_in_file",
    "update_spec_checklist",
    "register_model_candidate",
    "set_smart_candidate_for_benchmark",
    "set_active_smart_model",
    "download_file",
}


@dataclass
class EscalationEvent:
    """
    Estrutura do evento/estado ESCALATE_TO_SMART com dados diagnósticos completos.
    """
    event: str = "ESCALATE_TO_SMART"
    phase: str | None = None
    task: str = ""
    fast_model: str = ""
    iterations: int = 0
    stagnation_cycles: int = 0
    repeated_tools: list[str] = field(default_factory=list)
    last_action: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "event": self.event,
            "phase": self.phase,
            "task": self.task,
            "fast_model": self.fast_model,
            "iterations": self.iterations,
            "stagnation_cycles": self.stagnation_cycles,
            "repeated_tools": list(self.repeated_tools),
            "last_action": self.last_action,
            "reason": self.reason,
        }


class StagnationDetector:
    """
    Detector determinístico de estagnação do modelo FAST.
    """

    def __init__(
        self,
        max_stagnation_cycles: int = DEFAULT_MAX_STAGNATION_CYCLES,
        max_repeated_queries: int = DEFAULT_MAX_REPEATED_QUERIES,
    ):
        self.max_stagnation_cycles = max_stagnation_cycles
        self.max_repeated_queries = max_repeated_queries
        self.stagnation_cycles = 0
        self.action_history: list[dict] = []
        self.repeated_tools: list[str] = []
        self.last_action: str = ""
        self.consecutive_tool_failures: int = 0
        self.last_state_snapshot: dict | None = None
        self.signatures: list[tuple[str, bool]] = []
        self.stuck_reason: str | None = None

    @staticmethod
    def _signature(name: str, arguments: dict | None) -> str:
        """Identidade da ação ignorando campos que só justificam (reason etc.)."""

        cleaned = {
            key: value
            for key, value in (arguments or {}).items()
            if key not in {"reason", "justification", "description"}
        }

        return name + "|" + repr(sorted(cleaned.items(), key=lambda item: item[0]))

    def detect_stuck(self) -> str | None:
        """
        Padrões de travamento que não dependem de 'sem progresso':
        - a mesma ação falhando STUCK_SAME_ERROR_REPEATS vezes seguidas;
        - duas ações diferentes alternando por STUCK_ALTERNATING_CYCLES ciclos.
        """

        recent = self.signatures

        if len(recent) >= STUCK_SAME_ERROR_REPEATS:
            tail = recent[-STUCK_SAME_ERROR_REPEATS:]

            if len({sig for sig, _ in tail}) == 1 and all(not ok for _, ok in tail):
                return (
                    f"A mesma ação falhou {STUCK_SAME_ERROR_REPEATS} vezes seguidas "
                    f"({tail[0][0].split('|')[0]})."
                )

        if len(recent) >= STUCK_ALTERNATING_CYCLES:
            tail = [sig for sig, _ in recent[-STUCK_ALTERNATING_CYCLES:]]
            first, second = tail[0], tail[1]

            if first != second and all(
                sig == (first if index % 2 == 0 else second)
                for index, sig in enumerate(tail)
            ):
                return (
                    f"Duas ações alternando por {STUCK_ALTERNATING_CYCLES} ciclos "
                    f"({first.split('|')[0]} <-> {second.split('|')[0]})."
                )

        return None

    def is_progress_action(
        self,
        name: str,
        arguments: dict | None = None,
        result: dict | None = None,
        current_state: dict | None = None,
    ) -> bool:
        """
        Determina se a ação executada representa progresso real da tarefa.

        Regras:
        - Ferramenta que falhou NÃO é progresso;
        - save_memory sozinho NÃO é progresso se não houver mudança de estado;
        - Ferramentas de consulta/leitura NÃO são progresso por si só;
        - Modificação de arquivos, checklist com avanço real, registro/transição de modelo SÃO progresso;
        - Mudança detectável em phase ou next_action É progresso.
        """
        arguments = arguments or {}
        result = result or {}

        if not result.get("success", False):
            return False

        # Verifica se houve avanço explícito no TaskState do projeto
        if current_state and self.last_state_snapshot:
            old_phase = self.last_state_snapshot.get("current_phase")
            new_phase = current_state.get("current_phase")
            old_action = self.last_state_snapshot.get("next_action")
            new_action = current_state.get("next_action")

            if (new_phase and new_phase != old_phase) or (new_action and new_action != old_action):
                return True

        # Regra 9: save_memory sozinho não conta como progresso
        if name == "save_memory":
            return False

        # Ferramentas puramente de consulta/leitura
        if name in READ_ONLY_TOOLS:
            return False

        # Atualização do checklist da especificação
        if name == "update_spec_checklist":
            if result.get("already_in_state") is True:
                # O item já estava no estado desejado — não houve alteração real
                return False
            if result.get("acceptance_criteria_failed") is True:
                return False
            return True

        # Registro de novo candidato no registry
        if name == "register_model_candidate":
            if result.get("already_registered") is True:
                return False
            return True

        # Transição de modelo para benchmark ou adoção
        if name in {"set_smart_candidate_for_benchmark", "set_active_smart_model"}:
            return True

        # Rascunho de Skill gravado
        if name == "propose_skill":
            return True

        # Modificação real de arquivos no sistema
        if name in {"write_file", "replace_in_file", "download_file"}:
            return True

        # Comandos de terminal
        if name == "run_command":
            cmd = str(arguments.get("command", "")).strip().lower()
            # Comandos puramente de leitura/inspeção não contam como progresso de escrita
            inspection_cmds = {"pwd", "ls", "git status", "git branch", "cat", "head", "tail", "whoami"}
            if any(cmd == icmd or cmd.startswith(icmd + " ") for icmd in inspection_cmds):
                return False
            # Se for teste ou comando de alteração com sucesso
            return True

        return False

    def record_action(
        self,
        name: str,
        arguments: dict | None = None,
        result: dict | None = None,
        current_state: dict | None = None,
    ) -> bool:
        """
        Registra uma ação executada e avalia progresso vs estagnação.
        Retorna True se foi identificado progresso real, False caso contrário.
        """
        arguments = arguments or {}
        result = result or {}
        action_desc = f"{name}: {arguments}"
        self.last_action = action_desc

        success = bool(result.get("success", False))

        self.signatures.append((self._signature(name, arguments), success))
        self.signatures = self.signatures[-STUCK_ALTERNATING_CYCLES:]

        stuck = self.detect_stuck()
        if stuck:
            # Equivale a esgotar o limiar de estagnação: dispara a escalada existente.
            self.stuck_reason = stuck
            self.stagnation_cycles = max(self.stagnation_cycles, self.max_stagnation_cycles)

        # Diferenciação clara: falha de execução de ferramenta vs estagnação
        if not success:
            self.consecutive_tool_failures += 1
            # Falha de ferramenta não zera nem é somada como ciclo de estagnação de sucesso
            return False

        self.consecutive_tool_failures = 0

        is_prog = self.is_progress_action(name, arguments, result, current_state)

        if is_prog:
            self.reset()
            if current_state:
                self.last_state_snapshot = dict(current_state)
            return True

        # Executou com sucesso, mas sem progresso real
        self.stagnation_cycles += 1

        # Identifica ferramentas repetidas
        past_names = [e["name"] for e in self.action_history[-6:]]
        if name in past_names and name not in self.repeated_tools:
            self.repeated_tools.append(name)

        self.action_history.append({
            "name": name,
            "arguments": arguments,
            "result": result,
            "cycle": self.stagnation_cycles,
        })

        if current_state:
            self.last_state_snapshot = dict(current_state)

        return False

    def record_text_cycle(self, content: str = ""):
        """
        Registra um ciclo em que o modelo apenas produziu texto sem ferramentas,
        mas a tarefa continuou pendente.
        """
        self.stagnation_cycles += 1
        self.last_action = "Resposta em texto sem ação de ferramenta"

    def reset(self):
        """
        Reinicia contadores após transição real de estado.
        """
        self.stagnation_cycles = 0
        self.repeated_tools.clear()
        self.consecutive_tool_failures = 0
        self.signatures.clear()
        self.stuck_reason = None

    def is_stagnated(self) -> bool:
        """
        Retorna True se os ciclos de estagnação atingiram o limiar.
        """
        return self.stagnation_cycles >= self.max_stagnation_cycles

    def check_escalation(
        self,
        phase: str | None = None,
        task: str = "",
        fast_model: str = "",
        iteration: int = 0,
        last_action: str | None = None,
    ) -> tuple[bool, str, EscalationEvent | None]:
        """
        Verifica deterministamente se há necessidade de escalonamento para SMART.
        """
        if self.is_stagnated():
            reason = (
                f"Estagnação de raciocínio do modelo FAST ('{fast_model or 'fast'}'): "
                f"{self.stagnation_cycles} ciclos consecutivos de ferramentas executadas com sucesso "
                "sem produzir nenhuma transição de estado, decisão ou progresso verificável."
            )

            if self.stuck_reason:
                reason = f"Travamento do modelo FAST ('{fast_model or 'fast'}'): {self.stuck_reason}"

            event = self.create_escalation_event(
                phase=phase,
                task=task,
                fast_model=fast_model,
                iteration=iteration,
                last_action=last_action or self.last_action,
                reason=reason,
            )
            return True, reason, event

        return False, "", None

    def create_escalation_event(
        self,
        phase: str | None = None,
        task: str = "",
        fast_model: str = "",
        iteration: int = 0,
        last_action: str | None = None,
        reason: str = "",
    ) -> EscalationEvent:
        """
        Cria o evento ESCALATE_TO_SMART com diagnóstico completo.
        """
        return EscalationEvent(
            event="ESCALATE_TO_SMART",
            phase=phase,
            task=task,
            fast_model=fast_model,
            iterations=iteration,
            stagnation_cycles=self.stagnation_cycles,
            repeated_tools=list(self.repeated_tools),
            last_action=last_action or self.last_action or "Nenhuma ação recente",
            reason=reason or "Escalonamento para SMART solicitado devido a estagnação.",
        )
