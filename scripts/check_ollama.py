"""Verifica manualmente a conexão com o Ollama local (não é um teste automatizado)."""

import ollama


def main() -> None:
    response = ollama.chat(
        model="qwen3:8b",
        messages=[
            {
                "role": "user",
                "content": "Responda apenas: conexão local funcionando.",
            }
        ],
    )

    print(response.message.content)


if __name__ == "__main__":
    main()
