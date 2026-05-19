from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:1233/v1",
    api_key="lm-studio"
)

messages = [
    {
        "role": "system",
        "content": (
            "Jesteś Jarvisem, prywatnym asystentem użytkownika. "
            "Odpowiadasz po polsku, krótko i konkretnie. "
            "Nie udawaj, że możesz sterować komputerem, dopóki nie masz takiej funkcji."
        )
    }
]

print("Jarvis v1 uruchomiony.")
print("Napisz 'exit', żeby zakończyć.\n")

while True:
    user_input = input("Ty: ")

    if user_input.lower() in ["exit", "quit", "wyjdź", "koniec"]:
        print("Jarvis: Wyłączam się.")
        break

    messages.append({
        "role": "user",
        "content": user_input
    })

    try:
        response = client.chat.completions.create(
            model="local-model",
            messages=messages,
            temperature=0.7
        )

        answer = response.choices[0].message.content

        print("Jarvis:", answer)

        messages.append({
            "role": "assistant",
            "content": answer
        })

    except Exception as e:
        print("Błąd:", e)