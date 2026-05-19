import json
import webbrowser


WEBSITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "spotify": "https://open.spotify.com",
    "chatgpt": "https://chatgpt.com",
    "steam": "https://store.steampowered.com",
}


def parse_ai_json(text):
    if not isinstance(text, str):
        text = ""

    decoder = json.JSONDecoder()

    for index, character in enumerate(text):
        if character != "{":
            continue

        try:
            data, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue

        if isinstance(data, dict):
            return data

    return {
        "action": "chat",
        "response": text,
    }


def open_website(target):
    target = str(target).lower()
    url = WEBSITES.get(target)
    if not url:
        return False

    webbrowser.open(url)
    return True
