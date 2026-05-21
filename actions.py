import json
import os
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import quote

from path_utils import get_base_path
from text_utils import normalize_text


WEBSITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "chatgpt": "https://chatgpt.com",
}

OPEN_COMMANDS = ["otworz", "odpal", "wlacz", "open"]
CLOSE_COMMANDS = ["zamknij", "wylacz", "close"]
SPOTIFY_SEARCH_COMMANDS = [
    "pusc",
    "odtworz",
    "znajdz na spotify",
    "wyszukaj na spotify",
]

APPS_PATH = get_base_path() / "apps.json"
ALIASES_PATH = get_base_path() / "aliases.json"
PROCESSES_PATH = get_base_path() / "processes.json"


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


def load_aliases():
    if not ALIASES_PATH.exists():
        return {}

    try:
        with ALIASES_PATH.open("r", encoding="utf-8") as aliases_file:
            aliases = json.load(aliases_file)
    except json.JSONDecodeError:
        return {}

    if not isinstance(aliases, dict):
        return {}

    return {
        normalize_text(target): [
            normalize_text(alias)
            for alias in alias_list
            if isinstance(alias, str) and alias.strip()
        ]
        for target, alias_list in aliases.items()
        if isinstance(target, str) and isinstance(alias_list, list)
    }


def resolve_alias(target):
    target = normalize_text(target)

    for real_target, aliases in load_aliases().items():
        if target == real_target or target in aliases:
            return real_target

    return target


def contains_phrase(text, phrase):
    return f" {phrase} " in f" {text} "


def has_command(text, commands):
    return any(contains_phrase(text, command) for command in commands)


def target_names(target, aliases):
    names = [target]
    names.extend(aliases.get(target, []))
    return sorted(set(names), key=len, reverse=True)


def find_target(text, targets):
    aliases = load_aliases()

    for target in sorted(targets, key=len, reverse=True):
        target = normalize_text(target)
        for name in target_names(target, aliases):
            if contains_phrase(text, name):
                return target

    return None


def parse_spotify_search(text):
    for command in sorted(SPOTIFY_SEARCH_COMMANDS, key=len, reverse=True):
        prefix = f"{command} "
        if text.startswith(prefix):
            query = text[len(prefix) :].strip()
            if query:
                return {"action": "spotify_search", "query": query}

    return None


def parse_local_action(text):
    text = normalize_text(text)

    spotify_action = parse_spotify_search(text)
    if spotify_action:
        return spotify_action

    if has_command(text, OPEN_COMMANDS):
        website = find_target(text, WEBSITES.keys())
        if website:
            return {"action": "open_website", "target": website}

        app = find_target(text, load_apps().keys())
        if app:
            return {"action": "open_app", "target": app}

    if has_command(text, CLOSE_COMMANDS):
        process = find_target(text, load_processes().keys())
        if process:
            return {"action": "close_app", "target": process}

    return None


def open_website(target):
    target = resolve_alias(target)
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


def load_processes():
    if not PROCESSES_PATH.exists():
        return {}

    try:
        with PROCESSES_PATH.open("r", encoding="utf-8") as processes_file:
            processes = json.load(processes_file)
    except json.JSONDecodeError:
        return {}

    if not isinstance(processes, dict):
        return {}

    return {
        normalize_text(name): process_name
        for name, process_name in processes.items()
        if isinstance(name, str) and isinstance(process_name, str) and process_name
    }


def open_app(target):
    target = resolve_alias(target)
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


def close_app(target):
    target = resolve_alias(target)
    processes = load_processes()
    process_name = processes.get(target)

    if not process_name:
        return "unknown"

    result = subprocess.run(
        ["taskkill", "/IM", process_name, "/F"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if result.returncode != 0:
        return "not_running"

    return "closed"


def is_app_running(target):
    target = resolve_alias(target)
    processes = load_processes()
    process_name = processes.get(target)

    if not process_name:
        return False

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        creationflags=creationflags,
    )

    if result.returncode != 0:
        return False

    return process_name.lower() in result.stdout.lower()


def spotify_search(query):
    query = normalize_text(query)
    if not query:
        return False

    os.startfile(f"spotify:search:{quote(query)}")
    return True
