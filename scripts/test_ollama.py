import ollama


response = ollama.chat(
    model="qwen3:8b",
    messages=[
        {
            "role": "user",
            "content": "Responda apenas: conexão local funcionando."
        }
    ],
)

print(response.message.content)
