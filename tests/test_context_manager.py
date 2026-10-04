import pytest
from core.context.manager import ContextManager


def test_context_manager_anti_loop():
    cm = ContextManager(max_repeated_tool_calls=2)

    # 1ª execução
    warn1 = cm.record_tool_call("run_command", {"command": "git status"}, {"success": True})
    assert warn1 is None

    # 2ª execução idêntica
    warn2 = cm.record_tool_call("run_command", {"command": "git status"}, {"success": True})
    assert warn2 is None

    # 3ª execução idêntica -> dispara aviso de loop!
    warn3 = cm.record_tool_call("run_command", {"command": "git status"}, {"success": True})
    assert warn3 is not None
    assert "Aviso do Harness" in warn3
    assert "Não repita" in warn3
def test_context_manager_anti_loop_varying_reason():
    cm = ContextManager(max_repeated_tool_calls=2)

    # Execuções do mesmo comando mas com 'reason' diferente
    warn1 = cm.record_tool_call(
        "run_command",
        {"command": "command -v git", "reason": "motivo A"},
        {"success": True},
    )
    assert warn1 is None

    warn2 = cm.record_tool_call(
        "run_command",
        {"command": "command -v git", "reason": "motivo B diferente"},
        {"success": True},
    )
    assert warn2 is None

    # 3ª chamada deve disparar o aviso mesmo com motivo diferente
    warn3 = cm.record_tool_call(
        "run_command",
        {"command": "command -v git", "reason": "motivo C"},
        {"success": True},
    )
    assert warn3 is not None
    assert "Aviso do Harness" in warn3


def test_context_manager_check_loop():
    cm = ContextManager(max_repeated_tool_calls=2)

    # 1ª chamada
    is_loop, _ = cm.check_loop("run_command", {"command": "command -v git", "reason": "1"})
    assert is_loop is False
    cm.record_tool_call("run_command", {"command": "command -v git", "reason": "1"}, {"success": True})

    # 2ª chamada
    is_loop, _ = cm.check_loop("run_command", {"command": "command -v git", "reason": "2"})
    assert is_loop is False
    cm.record_tool_call("run_command", {"command": "command -v git", "reason": "2"}, {"success": True})

    # 3ª chamada -> check_loop deve acusar repetição antes de executar!
    is_loop, msg = cm.check_loop("run_command", {"command": "command -v git", "reason": "3"})
    assert is_loop is True
    assert "Ação bloqueada" in msg
    assert "command -v git" in msg

def test_context_manager_compaction():
    cm = ContextManager(max_context_chars=500)

    messages = [
        {"role": "system", "content": "System prompt com instrucoes"},
        {"role": "user", "content": "Tarefa inicial do usuario"},
    ]

    # Adiciona histórico que excede 500 caracteres
    for i in range(10):
        messages.append({
            "role": "assistant",
            "content": f"Pensamento e acao {i} " * 5,
        })
        messages.append({
            "role": "tool",
            "tool_name": "run_command",
            "content": f"resultado da ferramenta {i} com varios detalhes adicionais no arquivo /tmp/log_{i}.txt",
        })

    assert cm.should_compact(messages) is True

    compacted = cm.compact(messages)
    assert len(compacted) < len(messages)
    assert compacted[0]["role"] == "system"
    assert compacted[1]["role"] == "user"
    assert "RESUMO DE COMPACTAÇÃO" in compacted[2]["content"]
    assert cm.compaction_count == 1
