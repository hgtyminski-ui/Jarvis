import json
import os
import subprocess
import webbrowser
from pathlib import Path


WEBSITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "chatgpt": "https://chatgpt.com",
}

APPS_PATH = Path(__file__).with_name("apps.json")


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


def is_uri(command):
    if ":" not in command:
        return False

    if len(command) >= 2 and command[1] == ":" and command[0].isalpha():
        return False

    return True


def load_apps():
    if not APPS_PATH.exists():
        return {}

    try:
        with APPS_PATH.open("r", encoding="utf-8") as apps_file:
            apps = json.load(apps_file)
    except json.JSONDecodeError:
        return {}

    if not isinstance(apps, dict):
        return {}

    return {
        str(name).lower(): command
        for name, command in apps.items()
        if isinstance(name, str) and isinstance(command, str) and command
    }


def open_app(target):
    target = str(target).lower()
    apps = load_apps()
    command = apps.get(target)

    if not command:
        return "unknown"

    extension = Path(command).suffix.lower()
    if extension in [".url", ".lnk"] or is_uri(command):
        os.startfile(command)
        return "opened"

    subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return "opened"
