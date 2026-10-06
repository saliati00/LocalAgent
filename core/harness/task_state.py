class TaskState:

    def __init__(self, task: str):
        self.task = task
        self.status = "running"

        self.current_phase = None
        self.current_step = None
        self.next_action = None

        self.actions_completed = []

        self.tool_calls = 0
        self.successful_tools = 0
        self.failed_tools = 0

        self.last_tool = None
        self.last_tool_success = None
        self.last_failure_reason = None
        self.is_blocked = False
        self.block_reason = None
        self.needs_human_reason = None
        self.is_escalated = False
        self.escalation_event = None
        self.smart_status = None
        self.is_smart_available = None
        self.smart_diagnostic = None

        self.steps = []

    def set_progress(
        self,
        phase=None,
        current_step=None,
        next_action=None,
    ):
        if phase is not None:
            self.current_phase = phase

        if current_step is not None:
            self.current_step = current_step

        if next_action is not None:
            self.next_action = next_action

    def action_completed(self, action: str):

        if action and action not in self.actions_completed:
            self.actions_completed.append(action)

    def start_tool(
        self,
        name: str,
        arguments: dict,
    ):

        self.status = "waiting_tool"

        self.tool_calls += 1

        self.last_tool = name
        self.last_tool_success = None

        self.steps.append({
            "type": "tool_call",
            "tool": name,
            "arguments": arguments,
        })

    def finish_tool(
        self,
        name: str,
        result: dict,
    ):

        success = result.get(
            "success",
            False,
        )

        if success:
            self.successful_tools += 1
            self.last_failure_reason = None
        else:
            self.failed_tools += 1
            self.last_failure_reason = result.get("error", "Erro na execução da ferramenta")

        self.last_tool = name
        self.last_tool_success = success

        self.steps.append({
            "type": "tool_result",
            "tool": name,
            "success": success,
            "result": result,
        })

        self.status = "running"

    def model_response(
        self,
        content: str,
    ):

        self.steps.append({
            "type": "model_response",
            "content": content,
        })

        self.status = "waiting_model"

    def complete(self):

        self.status = "completed"

        self.current_step = "Tarefa concluída"

        self.next_action = None

    def fail(
        self,
        reason: str,
    ):

        self.status = "failed"

        self.current_step = "Tarefa falhou"

        self.next_action = None

        self.steps.append({
            "type": "task_error",
            "reason": reason,
        })

    def block(
        self,
        reason: str,
    ):

        self.status = "blocked"
        self.is_blocked = True
        self.block_reason = reason

        self.current_step = "Tarefa bloqueada"

        self.next_action = None

        self.steps.append({
            "type": "task_blocked",
            "reason": reason,
        })

    def needs_human(
        self,
        reason: str,
    ):
        """
        A tarefa não pode avançar sem uma ação do usuário (senha, decisão, aprovação).

        Diferente de cancelled (o usuário recusou) e de failed (erro técnico).
        """

        self.status = "needs_human"
        self.needs_human_reason = reason

        self.current_step = "Aguardando ação do usuário"

        self.next_action = None

        self.steps.append({
            "type": "needs_human",
            "reason": reason,
        })

    def cancel(
        self,
        reason: str,
    ):

        self.status = "cancelled"

        self.current_step = "Ação cancelada"

        self.next_action = None

        self.steps.append({
            "type": "task_cancelled",
            "reason": reason,
        })

    def escalate_to_smart(
        self,
        event_data: dict | None = None,
        reason: str = "",
    ):
        """
        Transiciona o estado da tarefa para solicitação de escalonamento para SMART.
        Registra diagnóstico completo no histórico de steps e no resumo da tarefa.
        """
        self.status = "escalate_to_smart"
        self.is_escalated = True

        if hasattr(event_data, "to_dict"):
            self.escalation_event = event_data.to_dict()
        elif isinstance(event_data, dict):
            self.escalation_event = dict(event_data)
        else:
            self.escalation_event = {
                "event": "ESCALATE_TO_SMART",
                "phase": self.current_phase,
                "task": self.task,
                "fast_model": "",
                "iterations": 0,
                "stagnation_cycles": 0,
                "repeated_tools": [],
                "last_action": self.last_tool or self.current_step or "",
                "reason": reason or "Escalonamento para SMART solicitado devido a estagnação.",
            }

        if reason and "reason" not in self.escalation_event:
            self.escalation_event["reason"] = reason

        self.current_step = "Escalonamento para SMART solicitado"
        self.next_action = None

        self.steps.append({
            "type": "escalate_to_smart",
            "data": self.escalation_event,
        })

    def resolve_escalation_smart_available(
        self,
        diagnostic: dict | None = None,
        reason: str = "",
    ):
        """
        Registra deterministamente que um modelo SMART está adotado e disponível para execução.
        Prepara a entrega da tarefa ao especialista SMART.
        """
        self.status = "smart_available"
        self.smart_status = "SMART_AVAILABLE"
        self.is_smart_available = True
        self.smart_diagnostic = dict(diagnostic or {})
        if reason and "reason" not in self.smart_diagnostic:
            self.smart_diagnostic["reason"] = reason

        model_name = self.smart_diagnostic.get("active_smart_model", "")
        self.current_step = f"SMART disponível ({model_name}): preparando entrega da tarefa"
        self.next_action = f"Executar tarefa com modelo especialista SMART ({model_name})"

        self.steps.append({
            "type": "smart_available",
            "data": self.smart_diagnostic,
        })

    def resolve_escalation_smart_unavailable(
        self,
        diagnostic: dict | None = None,
        reason: str = "",
    ):
        """
        Registra deterministamente que nenhum modelo SMART está adotado e disponível no momento.
        O agente NÃO é finalizado como uma falha genérica (failed), mas entra em condição operacional
        estruturada 'smart_unavailable', apontando a próxima capacidade necessária (selecionar/preparar SMART).
        """
        self.status = "smart_unavailable"
        self.smart_status = "SMART_UNAVAILABLE"
        self.is_smart_available = False
        self.smart_diagnostic = dict(diagnostic or {})
        if reason and "reason" not in self.smart_diagnostic:
            self.smart_diagnostic["reason"] = reason

        self.current_step = "SMART indisponível: aguardando seleção e preparação de modelo especialista"
        self.next_action = "Selecionar e preparar modelo SMART"

        self.steps.append({
            "type": "smart_unavailable",
            "data": self.smart_diagnostic,
        })

    def summary(self):

        return {
            "status": self.status,
            "current_phase": self.current_phase,
            "current_step": self.current_step,
            "next_action": self.next_action,
            "actions_completed": self.actions_completed,
            "tool_calls": self.tool_calls,
            "successful_tools": self.successful_tools,
            "failed_tools": self.failed_tools,
            "last_tool": self.last_tool,
            "last_tool_success": self.last_tool_success,
            "last_failure_reason": self.last_failure_reason,
            "is_blocked": self.is_blocked,
            "needs_human_reason": self.needs_human_reason,
            "is_escalated": self.is_escalated,
            "escalation_event": self.escalation_event,
            "smart_status": self.smart_status,
            "is_smart_available": self.is_smart_available,
            "smart_diagnostic": self.smart_diagnostic,
            "steps": len(self.steps),
        }
