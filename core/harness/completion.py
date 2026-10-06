import json
from pathlib import Path

from core.paths import REGISTRY_PATH



def get_continuation_guidance(
    current_phase: str | None = None,
    next_action: str | None = None,
    registry_path: Path | str | None = None,
    registry_data: dict | None = None,
) -> str | None:
    """
    Gera orientação operacional determinística para a próxima transição do projeto
    com base no estado atual do Model Registry e lifecycle.

    Não escolhe qual modelo adotar pelo LLM.
    Comunica claramente a próxima TRANSIÇÃO necessária e ferramentas cabíveis.
    Não hardcodeia nomes de modelos específicos.
    """
    if registry_data is not None:
        data = registry_data
    else:
        path = Path(registry_path) if registry_path else REGISTRY_PATH
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    models = data.get("models", {})
    active_smart = data.get("active_smart_model")

    smart_models = {k: v for k, v in models.items() if v.get("role") == "smart"}
    candidates = [k for k, v in smart_models.items() if v.get("status") == "candidate"]
    selected_for_bench = [k for k, v in smart_models.items() if v.get("status") == "selected_for_benchmark"]
    adopted = [k for k, v in smart_models.items() if v.get("status") == "adopted" or k == active_smart]

    # ESTADO: Candidato(s) SMART existem, mas nenhum foi selecionado para benchmark nem adotado
    if candidates and not selected_for_bench and not active_smart and not adopted:
        tool_name = "set_smart_candidate_for_benchmark"
        has_tool = False
        try:
            from tools.manager import TOOLS
            has_tool = tool_name in TOOLS
        except Exception:
            has_tool = True

        tool_ref = f"`{tool_name}`" if has_tool else f"a ferramenta apropriada de seleção ({tool_name})"

        return (
            "ESTADO ATUAL:\n"
            "SMART candidate ainda não foi selecionado para benchmark.\n\n"
            "PRÓXIMA TRANSIÇÃO:\n"
            "candidate → selected_for_benchmark.\n\n"
            "AÇÃO ESPERADA:\n"
            f"Avalie os candidatos e, se um candidato atender aos critérios, use {tool_ref}.\n\n"
            "NÃO fique apenas consultando novamente registry/status/memory sem produzir uma decisão ou executar a próxima transição.\n\n"
            "Se nenhum candidato for adequado, produza explicitamente `NO_SUITABLE_CANDIDATE` com justificativa/evidência."
        )

    return None


def build_continuation_reason(
    current_phase: str | None = None,
    next_action: str | None = None,
    base_reason: str | None = None,
    registry_path: Path | str | None = None,
    registry_data: dict | None = None,
) -> str:
    """
    Constrói a mensagem de motivo para CONTINUE combinando o status do projeto
    com a orientação operacional determinística caso aplicável.
    """
    guidance = get_continuation_guidance(
        current_phase=current_phase,
        next_action=next_action,
        registry_path=registry_path,
        registry_data=registry_data,
    )

    if not base_reason:
        phase_str = f" na {current_phase}" if current_phase else ""
        action_str = f"'{next_action}'" if next_action else "próxima etapa"
        base_reason = (
            f"O projeto possui a pendência ativa {action_str}{phase_str}. "
            "A etapa anterior foi processada; continue o desenvolvimento executando a próxima pendência."
        )

    if guidance:
        return f"{base_reason}\n\n{guidance}"

    return base_reason


def check_completion(
    model: str,
    task: str,
    response: str,
    tool_calls: int,
    successful_tools: int,
    failed_tools: int,
    actions_completed: list[str] | None = None,
    last_tool_success: bool | None = None,
    last_failure_reason: str | None = None,
    current_phase: str | None = None,
    next_action: str | None = None,
    registry_path: Path | str | None = None,
    registry_data: dict | None = None,
) -> dict:
    """
    Avalia se a resposta atual representa a conclusão da tarefa.

    O controller é conservador:
    - não considera uma simples explicação vazia como conclusão;
    - se a última ferramenta falhou ou foi bloqueada pelo Harness, NUNCA conclui;
    - exige evidência concreta de que o objetivo solicitado foi cumprido;
    - a simples chamada ou menção de 'update_spec_checklist' NÃO é prova de conclusão.
    """
    # Verificação determinística do Harness: falhas/bloqueios recentes impedem conclusão
    if last_tool_success is False:
        err_msg = last_failure_reason or "última ferramenta falhou ou foi bloqueada pelo Harness"
        base_msg = (
            f"A última ação de ferramenta falhou ou foi bloqueada ({err_msg}). "
            "A tarefa não pode ser concluída com erro ou bloqueio recente pendente."
        )
        reason = build_continuation_reason(
            current_phase=current_phase,
            next_action=next_action,
            base_reason=base_msg,
            registry_path=registry_path,
            registry_data=registry_data,
        )
        return {
            "status": "continue",
            "reason": reason,
        }

    # Se a resposta do modelo admite bloqueio de repetição ou erro sem recuperação
    resp_lower = (response or "").lower()
    if any(k in resp_lower for k in ["loop_blocked", "bloqueada para evitar loops", "bloqueada pelo harness"]):
        base_msg = "O agente relatou bloqueio por repetição do Harness. A tarefa precisa de recuperação e não está concluída."
        reason = build_continuation_reason(
            current_phase=current_phase,
            next_action=next_action,
            base_reason=base_msg,
            registry_path=registry_path,
            registry_data=registry_data,
        )
        return {
            "status": "continue",
            "reason": reason,
        }

    import ollama

    actions_str = ", ".join(actions_completed[-5:]) if actions_completed else "nenhuma ação registrada"

    prompt = f"""
Você é o controlador de conclusão de uma tarefa executada por outro agente.

Sua função NÃO é executar a tarefa.
Sua função é decidir se a tarefa realmente terminou com sucesso.

TAREFA / ETAPA SOLICITADA:
{task}

RESPOSTA ATUAL DO AGENTE:
{response}

INFORMAÇÕES DA EXECUÇÃO:
- chamadas de ferramentas: {tool_calls}
- ferramentas bem-sucedidas: {successful_tools}
- ferramentas que falharam: {failed_tools}
- ações concluídas: {actions_str}

REGRAS:

1. Só considere a tarefa concluída se o objetivo solicitado tiver sido efetivamente
   executado, validado e respondido com resultados reais.

2. Uma explicação genérica, sugestão vazia, plano futuro ou admissão de erro/bloqueio
   sem execução prática NÃO significa que a tarefa terminou. O resultado deve ser "continue".

3. Se a tarefa pedir uma ação prática e ferramentas ainda não tiverem sido executadas
   para verificar ou implementar o que foi pedido, o resultado deve ser "continue".

4. Se o agente tiver executado as ferramentas necessárias para cumprir a tarefa
   e apresentado evidências reais e validadas (como arquivos alterados com testes passando,
   saídas reais de comandos ou dados obtidos), o resultado pode ser "complete".
   IMPORTANTE: A mera marcação do checklist NÃO é evidência suficiente por si só;
   é necessária comprovação prática do trabalho executado.

5. Se a última ação de ferramenta falhou, foi bloqueada pelo Harness ou o agente
   está apenas relatando que uma ação foi impedida, o resultado NUNCA pode ser "complete",
   deve ser "continue".

6. Se as informações solicitadas já foram obtidas e claramente relatadas ao usuário,
   o resultado deve ser "complete". Não force iterações redundantes.

7. Seja objetivo e rigoroso. Na dúvida fundamentada, escolha "continue".

Responda SOMENTE com JSON válido:

{{
    "status": "complete" ou "continue",
    "reason": "explicação curta"
}}
"""

    try:
        result = ollama.chat(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "Você é um controlador de conclusão de tarefas rigoroso e objetivo.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            format="json",
            think=False,
            options={"num_ctx": 4096},
        )

        content = result.message.content

        decision = json.loads(content)

        status = decision.get("status")

        if status not in {"complete", "continue"}:
            base_msg = "Controlador retornou um status inválido."
            return {
                "status": "continue",
                "reason": build_continuation_reason(
                    current_phase=current_phase,
                    next_action=next_action,
                    base_reason=base_msg,
                    registry_path=registry_path,
                    registry_data=registry_data,
                ),
            }

        reason = decision.get(
            "reason",
            "Sem justificativa fornecida.",
        )
        if status == "continue":
            reason = build_continuation_reason(
                current_phase=current_phase,
                next_action=next_action,
                base_reason=reason,
                registry_path=registry_path,
                registry_data=registry_data,
            )

        return {
            "status": status,
            "reason": reason,
        }

    except Exception as e:
        base_msg = f"Falha no controlador de conclusão: {e}"
        return {
            "status": "continue",
            "reason": build_continuation_reason(
                current_phase=current_phase,
                next_action=next_action,
                base_reason=base_msg,
                registry_path=registry_path,
                registry_data=registry_data,
            ),
        }
