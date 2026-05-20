import json

from actions import (
    close_app,
    open_app,
    open_website,
    parse_ai_json,
    parse_local_action,
    resolve_alias,
)
from config import ConfigError, load_config
from memory import add_assistant_message, add_user_message, clear_messages, create_messages
from text_utils import normalize_text


def show_help():
    print("Dostępne komendy:")
    print("/help - pokazuje dostępne komendy")
    print("/exit - kończy program")
    print("/status - sprawdza połączenie z LM Studio")
    print("/clear - czyści historię rozmowy z RAM")
    print("/listen - nagrywa krótką wiadomość z mikrofonu")
    print("/close <aplikacja> - zamyka aplikację z processes.json")


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

    local_action = parse_local_action(command.lstrip("/"))
    if local_action:
        handle_ai_answer(json.dumps(local_action), assistant_name, config)
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
        target = resolve_alias(data.get("target", ""))
        if open_website(target):
            print(f"{assistant_name}: Otwieram stronę: {target}")
        else:
            print(f"{assistant_name}: Nie obsługuję tej strony.")
        return

    if action == "open_app":
        target = resolve_alias(data.get("target", ""))

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

    if action == "close_app":
        target = resolve_alias(data.get("target", ""))

        try:
            result = close_app(target)
        except Exception as e:
            print(f"{assistant_name}: Nie udało się zamknąć aplikacji: {target}")
            print("Błąd:", e)
            return

        if result == "closed":
            print(f"{assistant_name}: Zamykam {target}.")
        elif result == "not_running":
            print(f"{assistant_name}: Nie znalazłem uruchomionego procesu dla: {target}.")
        else:
            print(f"{assistant_name}: Nie znam aplikacji: {target}. Dodaj ją do processes.json.")
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

        normalized_user_input = normalize_text(user_input)
        normalized_exit_commands = [
            normalize_text(command) for command in config["exit_commands"]
        ]

        if normalized_user_input in normalized_exit_commands:
            print(f"{assistant_name}: Wyłączam się. Do zobaczenia!")
            break

        local_action = parse_local_action(user_input)
        if local_action:
            handle_ai_answer(json.dumps(local_action), assistant_name, config)
            continue

        add_user_message(messages, normalized_user_input)

        try:
            answer = get_ai_response(client, messages, config)

            handle_ai_answer(answer, assistant_name, config)

            add_assistant_message(messages, answer)

        except Exception as e:
            print("Błąd:", e)


if __name__ == "__main__":
    main()
