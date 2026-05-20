from actions import load_apps, load_processes


ACTION_INSTRUCTIONS = (
    "\n\nZawsze odpowiadaj wyłącznie JSON-em. "
    'Dla zwykłej rozmowy użyj formatu: {"action": "chat", "response": "odpowiedź"}. '
    'Jeśli użytkownik chce otworzyć stronę, użyj formatu: {"action": "open_website", "target": "youtube"}. '
    'Jeśli użytkownik chce otworzyć aplikację, użyj formatu: {"action": "open_app", "target": "notepad"}. '
    'Jeśli użytkownik chce zamknąć aplikację, użyj formatu: {"action": "close_app", "target": "spotify"}. '
    "Obsługiwane strony: youtube, google, chatgpt. "
    "Obsługiwane aplikacje są zdefiniowane w apps.json. "
    "Procesy do zamykania są zdefiniowane w processes.json. "
    "Nie dodawaj tekstu poza JSON-em."
)


def get_action_instructions():
    app_names = ", ".join(load_apps().keys()) or "brak"
    process_names = ", ".join(load_processes().keys()) or "brak"
    return (
        ACTION_INSTRUCTIONS
        + f" Obsługiwane aplikacje: {app_names}."
        + f" Aplikacje do zamykania: {process_names}."
    )


def create_messages(config):
    return [
        {
            "role": "system",
            "content": config["system_message"] + get_action_instructions(),
        }
    ]


def add_user_message(messages, content):
    messages.append(
        {
            "role": "user",
            "content": content,
        }
    )


def clear_messages(messages, config):
    messages.clear()
    messages.extend(create_messages(config))


def add_assistant_message(messages, content):
    messages.append(
        {
            "role": "assistant",
            "content": content,
        }
    )
