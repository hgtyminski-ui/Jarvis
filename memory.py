ACTION_INSTRUCTIONS = (
    "\n\nZawsze odpowiadaj wyłącznie JSON-em. "
    'Dla zwykłej rozmowy użyj formatu: {"action": "chat", "response": "odpowiedź"}. '
    'Jeśli użytkownik chce otworzyć stronę, użyj formatu: {"action": "open_website", "target": "youtube"}. '
    "Obsługiwane strony: youtube, google, spotify, chatgpt, steam. "
    "Nie dodawaj tekstu poza JSON-em."
)


def create_messages(config):
    return [
        {
            "role": "system",
            "content": config["system_message"] + ACTION_INSTRUCTIONS,
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
