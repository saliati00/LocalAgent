"""Verifica a conexao com o Ollama local e se o modelo principal esta instalado (nao e um teste automatizado)."""

import json
import sys
from pathlib import Path

import ollama

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.console import ensure_utf8_console  # noqa: E402

REGISTRY = Path(__file__).resolve().parent.parent / "models" / "registry.json"


def main() -> int:
    ensure_utf8_console()

    model = "qwen3:8b"

    try:
        model = json.loads(REGISTRY.read_text(encoding="utf-8")).get("active_fast_model") or model
    except Exception:
        pass

    try:
        installed = [m.model for m in ollama.list().models]
    except Exception:
        print("NAO FOI POSSIVEL falar com o Ollama.")
        print("Abra o programa Ollama (menu Iniciar) ou rode iniciar.bat, e tente de novo.")
        return 1

    if not any(name == model or name.startswith(model + ":") or model.startswith(name) for name in installed):
        print(f"O Ollama esta funcionando, mas o modelo {model} nao foi baixado.")
        print(f"Para baixar, abra o Prompt de Comando e rode:  ollama pull {model}")
        return 1

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": "Responda apenas: conexao local funcionando."}],
    )

    print(f"Modelo {model} respondeu:", response.message.content)

    return 0


if __name__ == "__main__":
    sys.exit(main())
