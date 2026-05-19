from config import ConfigError, load_config
from memory import add_assistant_message, add_user_message, clear_messages, create_messages


def show_help():
    print("Dostępne komendy:")
    print("/help - pokazuje dostępne komendy")
    print("/exit - kończy program")
    print("/status - sprawdza połączenie z LM Studio")
    print("/clear - czyści historię rozmowy z RAM")


def handle_local_command(command, assistant_name, client, config, messages):
    if command == "/help":
        show_help()
        return False

    if command == "/exit":
        print(f"{assistant_name}: Wyłączam się. Do zobaczenia!")
        return True

    if command == "/status":
        from ai_client import check_connection

        try:
            check_connection(client, config)
            print("Status: połączenie z LM Studio działa.")
        except Exception as e:
            print("Status: brak połączenia z LM Studio.")
            print("Błąd:", e)
        return False

    if command == "/clear":
        clear_messages(messages, config)
        print("Historia rozmowy w RAM została wyczyszczona.")
        return False

    print("Nieznana komenda lokalna. Wpisz /help, aby zobaczyć dostępne komendy.")
    return False


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

        if user_input.startswith("/"):
            should_exit = handle_local_command(
                user_input.strip().lower(),
                assistant_name,
                client,
                config,
                messages,
            )
            if should_exit:
                break
            continue

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
