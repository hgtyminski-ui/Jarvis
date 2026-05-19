from config import ConfigError, load_config
from memory import add_assistant_message, add_user_message, create_messages


def main():
    try:
        config = load_config()
    except ConfigError as e:
        print("Błąd konfiguracji:", e)
        return

    from ai_client import create_client, get_ai_response

    assistant_name = config["assistant_name"]
    client = create_client(config)
    messages = create_messages(config)

    print(f"{assistant_name} uruchomiony.")
    print("Napisz 'exit', żeby zakończyć.\n")

    while True:
        user_input = input("Ty: ")

        if user_input.lower() in config["exit_commands"]:
            print(f"{assistant_name}: Wyłączam się. Do zobaczenia!")
            break

        add_user_message(messages, user_input)

        try:
            answer = get_ai_response(client, messages, config)

            print(f"{assistant_name}:", answer)

            add_assistant_message(messages, answer)

        except Exception as e:
            print("Błąd:", e)


if __name__ == "__main__":
    main()
