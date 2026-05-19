from ai_client import create_client, get_ai_response
from config import EXIT_COMMANDS
from memory import add_assistant_message, add_user_message, create_messages


def main():
    client = create_client()
    messages = create_messages()

    print("Jarvis uruchomiony.")
    print("Napisz 'exit', żeby zakończyć.\n")

    while True:
        user_input = input("Ty: ")

        if user_input.lower() in EXIT_COMMANDS:
            print("Jarvis: Wyłączam się. Do zobaczenia!")
            break

        add_user_message(messages, user_input)

        try:
            answer = get_ai_response(client, messages)

            print("Jarvis:", answer)

            add_assistant_message(messages, answer)

        except Exception as e:
            print("Błąd:", e)


if __name__ == "__main__":
    main()
