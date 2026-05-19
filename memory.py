from config import SYSTEM_MESSAGE


def create_messages():
    return [
        {
            "role": "system",
            "content": SYSTEM_MESSAGE,
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
