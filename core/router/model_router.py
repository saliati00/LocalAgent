import json
from pathlib import Path
import subprocess
from typing import Any


REGISTRY_PATH = Path("/home/bruno/local-agent/models/registry.json")


COMPLEX_TASK_KEYWORDS = [
    "refatorar",
    "arquitetura",
    "benchmark de contexto",
    "quantização complexa",
    "analisar benchmark",
    "otimização profunda",
    "llama.cpp",
]


class ModelRouter:
    """
    Roteador de Modelos e Controlador de Escalada do Harness.

    Responsável por:
    - Consultar o Model Registry;
    - Selecionar o modelo mais adequado (FAST vs SMART);
    - Avaliar necessidade de escalada automática quando o modelo operador
      encontra dificuldades consecutivas.

    FAST e SMART são papéis arquiteturais — o tamanho do modelo é apenas
    um atributo factual do candidato, não um requisito do papel.
    """

    def __init__(self, registry_path: Path | None = None):
        self.registry_path = registry_path or REGISTRY_PATH
        self._data = self._load_registry()

    def _load_registry(self) -> dict:
        if not self.registry_path.exists():
            return {
                "active_fast_model": None,
                "active_smart_model": None,
                "models": {},
            }

        try:
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception:
            return {
                "active_fast_model": None,
                "active_smart_model": None,
                "models": {},
            }

    def save_registry(self):
        try:
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            self.registry_path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    def get_fast_model(self) -> str | None:
        """
        Retorna o modelo FAST ativo conforme registrado no Model Registry.
        Retorna None se nenhum modelo FAST estiver definido no registry.
        O papel FAST é determinado pelo registry, não por um nome hardcoded.
        """
        return self._data.get("active_fast_model") or None

    def get_smart_model(self) -> str | None:
        """
        Retorna o modelo SMART ativo, ou None se nenhum tiver sido adotado.
        O papel SMART é determinado pelo registry, não pelo tamanho do modelo.
        """
        return self._data.get("active_smart_model") or None

    def route_task(self, prompt: str, current_phase: str | None = None) -> str | None:
        """
        Determina qual modelo deve iniciar a tarefa com base na complexidade.
        Usa o modelo FAST como padrão. Escala para SMART quando disponível e necessário.

        Retorna o nome do modelo selecionado, ou None se nenhum modelo estiver definido no registry.
        O modelo FAST é determinado pelo registry — nenhum nome de modelo é assumido por padrão.
        """
        text = prompt.lower()

        # Verifica se o usuário pediu explicitamente um modelo SMART/especialista
        if "smart" in text or "especialista" in text:
            smart_model = self.get_smart_model()
            if smart_model:
                smart_info = self._data.get("models", {}).get(smart_model, {})
                if smart_info.get("status") == "installed":
                    return smart_model

        # Tarefas que exigem raciocínio avançado (apenas quando SMART disponível e instalado)
        is_complex = any(kw in text for kw in COMPLEX_TASK_KEYWORDS)
        if is_complex and current_phase and "FASE 3" in current_phase:
            smart_model = self.get_smart_model()
            if smart_model:
                smart_info = self._data.get("models", {}).get(smart_model, {})
                if smart_info.get("status") == "installed":
                    return smart_model

        # Por padrão, utiliza o modelo FAST como operador inicial.
        # O modelo FAST é resolvido via registry — não existe fallback hardcoded.
        return self.get_fast_model()


    def should_escalate(
        self,
        consecutive_errors: int = 0,
        iteration: int = 0,
        tool_failures: int = 0,
        stagnation_cycles: int = 0,
        max_stagnation_cycles: int = 6,
        stagnation_reason: str = "",
    ) -> tuple[bool, str]:
        """
        Avalia se a tarefa deve ser escalada para um modelo SMART.
        Retorna (deve_escalar, motivo).

        Diferencia determinística e claramente:
        - Erros consecutivos de ferramentas (falha técnica de execução);
        - Iterações excessivas com alto índice de falhas;
        - Estagnação de raciocínio do FAST (ciclos de ferramentas bem-sucedidas sem progresso real).
        """
        if consecutive_errors >= 3:
            return (
                True,
                f"O modelo acumulou {consecutive_errors} erros consecutivos na mesma tarefa.",
            )

        if iteration >= 18 and tool_failures > 5:
            return (
                True,
                f"Muitas iterações ({iteration}) com alto índice de falhas de ferramentas ({tool_failures}).",
            )

        if stagnation_cycles >= max_stagnation_cycles:
            return (
                True,
                stagnation_reason
                or f"Estagnação de raciocínio detectada: {stagnation_cycles} ciclos consecutivos sem progresso útil.",
            )

        return False, ""

    def register_model(
        self,
        name: str,
        role: str,
        backend: str,
        status: str = "candidate",
        **kwargs,
    ):
        """
        Adiciona ou atualiza um modelo no registry.
        role deve ser 'fast' ou 'smart' — não depende do tamanho do modelo.
        """
        if "models" not in self._data:
            self._data["models"] = {}

        model_entry = {
            "name": name,
            "role": role,
            "backend": backend,
            "status": status,
            **kwargs,
        }
        self._data["models"][name] = model_entry
        self.save_registry()

    def set_model_status(self, name: str, status: str):
        if "models" in self._data and name in self._data["models"]:
            self._data["models"][name]["status"] = status
            self.save_registry()

    def list_models(self) -> dict:
        return self._data.get("models", {})

    def is_model_installed(
        self,
        model_name: str,
        backend_checker: Any = None,
    ) -> bool:
        """
        Valida deterministicamente se o modelo está realmente disponível no backend de execução.
        Não confia apenas no JSON — consulta o backend real (ex: 'ollama list').
        """
        if backend_checker is not None:
            return bool(backend_checker(model_name))

        target = model_name.lower().strip()
        target_tag = target if ":" in target else f"{target}:latest"

        try:
            res = subprocess.run(
                ["ollama", "list"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode != 0:
                return False

            for line in res.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if not parts:
                    continue
                name_in_list = parts[0].lower().strip()
                name_tag = name_in_list if ":" in name_in_list else f"{name_in_list}:latest"
                if target == name_in_list or target_tag == name_tag:
                    return True
            return False
        except Exception:
            return False

    def check_smart_availability(
        self,
        backend_checker: Any = None,
    ) -> tuple[bool, str, dict]:
        """
        Verifica deterministicamente se existe um modelo SMART adotado e disponível para execução.

        Critérios de validação:
        1. active_smart_model deve estar preenchido (não pode ser null/None);
        2. O modelo deve existir no bloco 'models' com role='smart';
        3. O status do modelo NÃO pode ser 'candidate' nem 'selected_for_benchmark'
           (somente modelos formalmente adotados/instalados são elegíveis);
        4. O modelo deve estar realmente instalado no backend de execução.

        Retorna: (is_available, motivo, diagnostic_dict)
        """
        smart_model = self.get_smart_model()

        if not smart_model:
            reason = "Nenhum modelo SMART adotado como active_smart_model no Model Registry."
            diagnostic = {
                "event": "SMART_UNAVAILABLE",
                "active_smart_model": None,
                "is_installed": False,
                "required_capability": "select_and_prepare_smart",
                "reason": reason,
            }
            return False, reason, diagnostic

        models = self.list_models()
        if smart_model not in models:
            reason = (
                f"O modelo '{smart_model}' está configurado como active_smart_model, "
                "mas não possui registro correspondente no bloco 'models'."
            )
            diagnostic = {
                "event": "SMART_UNAVAILABLE",
                "active_smart_model": smart_model,
                "is_installed": False,
                "required_capability": "select_and_prepare_smart",
                "reason": reason,
            }
            return False, reason, diagnostic

        smart_info = models[smart_model]
        role = str(smart_info.get("role", "")).lower()
        if role != "smart":
            reason = f"O modelo '{smart_model}' possui role '{role}', não sendo reconhecido como SMART."
            diagnostic = {
                "event": "SMART_UNAVAILABLE",
                "active_smart_model": smart_model,
                "is_installed": False,
                "required_capability": "select_and_prepare_smart",
                "reason": reason,
            }
            return False, reason, diagnostic

        status = str(smart_info.get("status", "")).lower()
        if status in {"candidate", "selected_for_benchmark"}:
            reason = (
                f"O modelo '{smart_model}' possui status '{status}' no registry, "
                "sendo apenas um candidato em avaliação e não um modelo SMART formalmente adotado."
            )
            diagnostic = {
                "event": "SMART_UNAVAILABLE",
                "active_smart_model": smart_model,
                "is_installed": False,
                "required_capability": "select_and_prepare_smart",
                "reason": reason,
            }
            return False, reason, diagnostic

        is_installed = self.is_model_installed(smart_model, backend_checker=backend_checker)
        if not is_installed:
            reason = (
                f"O modelo SMART '{smart_model}' está configurado no registry, "
                "mas não foi encontrado instalado no backend de execução."
            )
            diagnostic = {
                "event": "SMART_UNAVAILABLE",
                "active_smart_model": smart_model,
                "is_installed": False,
                "required_capability": "select_and_prepare_smart",
                "reason": reason,
            }
            return False, reason, diagnostic

        reason = f"Modelo SMART '{smart_model}' formalmente adotado e disponível no backend para execução."
        diagnostic = {
            "event": "SMART_AVAILABLE",
            "active_smart_model": smart_model,
            "is_installed": True,
            "required_capability": None,
            "reason": reason,
        }
        return True, reason, diagnostic

