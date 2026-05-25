from config import ConfigError, load_config
from jarvis_core import (
    handle_ai_answer as core_handle_ai_answer,
    handle_local_command as core_handle_local_command,
    process_user_text as core_process_user_text,
    show_help_text,
)
from memory import create_messages


def print_result(result):
    if result and result.response:
        print(result.response)


def show_help():
    print(show_help_text())


def handle_local_command(command, assistant_name, client, config, messages):
    result = core_handle_local_command(command, assistant_name, client, config, messages)
    print_result(result)
    return result.should_exit


def handle_ai_answer(answer, assistant_name, config):
    result = core_handle_ai_answer(answer, assistant_name, config)
    print_result(result)
    return result


def process_user_text(user_input, assistant_name, client, config, messages, pending_note=None):
    result = core_process_user_text(
        user_input,
        assistant_name,
        client,
        config,
        messages,
        pending_note,
    )
    print_result(result)

    if config.get("voice_enabled", False) and result.tts_text:
        from voice import speak

        speak(result.tts_text)

    return result.should_exit


def main():
    try:
        config = load_config()
    except ConfigError as e:
        print("Blad konfiguracji:", e)
        return

    from ai_client import create_client

    assistant_name = config["assistant_name"]
    client = create_client(config)
    messages = create_messages(config)
    pending_note = {}

    print(f"{assistant_name} uruchomiony.")
    print("Napisz 'exit', zeby zakonczyc.\n")

    while True:
        user_input = input("Ty: ")

        if user_input.strip().lower() == "/listen":
            from speech_input import listen_once

            spoken_text = listen_once()
            if not spoken_text:
                continue

            print("Ty:", spoken_text)
            user_input = spoken_text

        if process_user_text(user_input, assistant_name, client, config, messages, pending_note):
            break


if __name__ == "__main__":
    main()
