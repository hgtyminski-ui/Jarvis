def create_messages(config):
    return [
        {
            "role": "system",
            "content": config["system_message"],
        }
    ]


def add_user_message(messages, content):
    messages.append(
        {
            "role": "user",
            "content": content,
        }
    )


def add_assistant_message(messages, content):
    messages.append(
        {
            "role": "assistant",
            "content": content,
        }
    )
