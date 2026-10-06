import json
from typing import Any


class ContextManager:
    """
    Gerenciador de Contexto e Anti-Looping do Harness.

    Responsabilidades:
    1. Monitorar o crescimento do contexto ativo;
    2. Realizar compactação estruturada quando ultrapassar limites seguros;
    3. Detectar e interromper loops de repetição de ferramentas idênticas;
    4. Preservar o objetivo original, estado, decisões e últimas ações.
    """

    def __init__(
        self,
        max_context_chars: int = 25000,
        max_repeated_tool_calls: int = 2,
    ):
        self.max_context_chars = max_context_chars
        self.max_repeated_tool_calls = max_repeated_tool_calls
        self.tool_history: list[dict] = []
        self.compaction_count: int = 0
        self.compaction_requested: bool = False

    def request_compaction(self) -> None:
        """Pede compactação na próxima preparação, mesmo abaixo do limite de caracteres."""

        self.compaction_requested = True

    def _normalize_arguments(self, name: str, arguments: dict) -> dict:
        if not isinstance(arguments, dict):
            return {}
        if name == "run_command":
            return {"command": str(arguments.get("command", "")).strip()}
        if name in {"read_file", "write_file", "list_directory"}:
            norm = {"path": str(arguments.get("path", "")).strip()}
            if "start_line" in arguments:
                norm["start_line"] = arguments.get("start_line")
            if "end_line" in arguments:
                norm["end_line"] = arguments.get("end_line")
            return norm
        if name == "replace_in_file":
            return {
                "path": str(arguments.get("path", "")).strip(),
                "target": str(arguments.get("target", "")).strip(),
            }
        if name == "web_search":
            return {"query": str(arguments.get("query", "")).strip().lower()}
        if name == "fetch_url":
            return {"url": str(arguments.get("url", "")).strip()}
        if name == "update_spec_checklist":
            return {
                "item": str(arguments.get("item", "")).strip().lower(),
                "completed": bool(arguments.get("completed", True)),
            }
        return {k: v for k, v in arguments.items() if k not in {"reason", "justification", "description"}}

    def check_loop(self, name: str, arguments: dict) -> tuple[bool, str | None]:
        """
        Verifica PREVIAMENTE se a chamada atual é uma repetição consecutiva
        de uma ação que já foi executada e teve sucesso recentemente.
        """
        norm_args = self._normalize_arguments(name, arguments)
        repeat_count = 0
        for past_call in reversed(self.tool_history):
            if (
                past_call["name"] == name
                and past_call["norm_args"] == norm_args
                and past_call["success"] is True
            ):
                repeat_count += 1
            else:
                break

        if repeat_count >= self.max_repeated_tool_calls:
            cmd_desc = norm_args.get("command") or norm_args.get("path") or norm_args
            return (
                True,
                (
                    f"Aviso do Harness: A ferramenta '{name}' com o alvo/comando '{cmd_desc}' "
                    f"já foi executada com sucesso {repeat_count} vezes recentemente. "
                    "Ação bloqueada para evitar loops de repetição. Não repita esta ação; "
                    "analise o que já foi obtido ou passe para a próxima verificação/etapa."
                ),
            )
        return False, None

    def record_tool_call(self, name: str, arguments: dict, result: dict) -> str | None:
        """
        Registra a execução de uma ferramenta e verifica se o modelo
        entrou em um loop de repetição com os mesmos argumentos e resultado.

        Retorna uma mensagem de aviso/bloqueio se loop for detectado, ou None.
        """
        norm_args = self._normalize_arguments(name, arguments)
        signature = {
            "name": name,
            "arguments": arguments,
            "norm_args": norm_args,
            "success": result.get("success", False),
        }

        # Conta ocorrências consecutivas recentes idênticas (normalizadas)
        repeat_count = 0
        for past_call in reversed(self.tool_history):
            if (
                past_call["name"] == name
                and past_call["norm_args"] == norm_args
                and past_call["success"] == signature["success"]
            ):
                repeat_count += 1
            else:
                break

        self.tool_history.append(signature)

        if repeat_count >= self.max_repeated_tool_calls:
            return (
                f"Aviso do Harness: A ferramenta '{name}' com os argumentos {arguments} "
                f"já foi executada {repeat_count + 1} vezes com o mesmo resultado. "
                "Não repita a mesma chamada. Analise o resultado já obtido ou tente uma ação diferente."
            )

        return None

    def calculate_chars(self, messages: list[dict]) -> int:
        """
        Calcula o total de caracteres de texto nas mensagens.
        """
        total = 0
        for msg in messages:
            content = msg.get("content") if hasattr(msg, "get") else getattr(msg, "content", None)
            if isinstance(content, str):
                total += len(content)
            elif content is not None:
                total += len(str(content))
        return total

    def should_compact(self, messages: list[dict]) -> bool:
        """
        Determina se o histórico de mensagens precisa ser compactado.
        """
        return self.calculate_chars(messages) >= self.max_context_chars

    def compact(self, messages: list[dict]) -> list[dict]:
        """
        Compacta a lista de mensagens preservando:
        - System prompt (messages[0])
        - Prompt original do usuário (messages[1])
        - Resumo estruturado das ações intermediárias
        - Últimas N mensagens (fluxo recente)
        """
        if len(messages) <= 6:
            return messages

        system_msg = messages[0]
        initial_user_msg = messages[1]
        recent_messages = messages[-4:]

        # Mensagens a serem compactadas (intermediárias)
        middle_messages = messages[2:-4]

        tools_executed = []
        errors_encountered = []
        files_accessed = set()

        for msg in middle_messages:
            role = msg.get("role") if hasattr(msg, "get") else getattr(msg, "role", None)
            tool_name = msg.get("tool_name") if hasattr(msg, "get") else getattr(msg, "tool_name", None)
            content = msg.get("content", "") if hasattr(msg, "get") else getattr(msg, "content", "")

            if role == "tool":
                tools_executed.append(tool_name or "ferramenta")
                if "error" in str(content).lower() or "'success': false" in str(content).lower():
                    errors_encountered.append(f"{tool_name}: {str(content)[:120]}")

            # Registra arquivos mencionados
            if isinstance(content, str):
                for word in content.split():
                    if word.startswith("/") or word.endswith((".py", ".md", ".txt", ".json")):
                        files_accessed.add(word.strip("',\"()[]{}"))

        self.compaction_count += 1

        summary_content = f"""
=========================================================
[HARNESS] RESUMO DE COMPACTAÇÃO #{self.compaction_count}
=========================================================
O histórico anterior foi compactado para economizar contexto.

Ações intermediárias compactadas: {len(middle_messages)} mensagens.
Ferramentas executadas no período: {", ".join(tools_executed[-10:]) if tools_executed else "nenhuma"}
Erros observados no período: {len(errors_encountered)}
Arquivos relevantes identificados: {", ".join(list(files_accessed)[:10]) if files_accessed else "nenhum"}

Continue a execução a partir do estado atual e das mensagens recentes abaixo.
=========================================================
"""

        summary_msg = {
            "role": "user",
            "content": summary_content.strip(),
        }

        compacted = [system_msg, initial_user_msg, summary_msg] + recent_messages
        return compacted

    def prepare_messages(self, messages: list[dict]) -> list[dict]:
        """
        Prepara as mensagens antes de enviar ao modelo, aplicando compactação se necessário.
        """
        if self.compaction_requested or self.should_compact(messages):
            self.compaction_requested = False
            return self.compact(messages)
        return messages
