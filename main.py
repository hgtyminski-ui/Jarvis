from actions import open_app, open_website, parse_ai_json
from config import ConfigError, load_config
from memory import add_assistant_message, add_user_message, clear_messages, create_messages


def show_help():
    print("Dostępne komendy:")
    print("/help - pokazuje dostępne komendy")
    print("/exit - kończy program")
    print("/status - sprawdza połączenie z LM Studio")
    print("/clear - czyści historię rozmowy z RAM")
    print("/listen - nagrywa krótką wiadomość z mikrofonu")


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


def handle_ai_answer(answer, assistant_name, config):
    data = parse_ai_json(answer)
    action = data.get("action")

    if action == "chat":
        response = data.get("response", "")
        print(f"{assistant_name}:", response)

        if config.get("voice_enabled", False):
            from voice import speak

            speak(response)
        return

    if action == "open_website":
        target = str(data.get("target", "")).lower()
        if open_website(target):
            print(f"{assistant_name}: Otwieram stronę: {target}")
        else:
            print(f"{assistant_name}: Nie obsługuję tej strony.")
        return

    if action == "open_app":
        target = str(data.get("target", "")).lower()

        try:
            result = open_app(target)
        except Exception as e:
            print(f"{assistant_name}: Nie udało się uruchomić aplikacji: {target}")
            print("Błąd:", e)
            return

        if result == "opened":
            print(f"{assistant_name}: Otwieram aplikację: {target}")
        else:
            print(f"{assistant_name}: Nie znam aplikacji: {target}. Dodaj ją do apps.json.")
        return

    print(f"{assistant_name}: Nie rozumiem akcji zwróconej przez AI.")


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

        if user_input.strip().lower() == "/listen":
            from speech_input import listen_once

            spoken_text = listen_once()
            if not spoken_text:
                continue

            print("Ty:", spoken_text)
            user_input = spoken_text

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

            handle_ai_answer(answer, assistant_name, config)

            add_assistant_message(messages, answer)

        except Exception as e:
            print("Błąd:", e)


if __name__ == "__main__":
    main()
