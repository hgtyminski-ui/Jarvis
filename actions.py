import json
import os
import re
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from path_utils import get_base_path
from notes_manager import (
    build_note_title,
    create_note as create_note_file,
    delete_note as delete_note_file,
    list_notes as list_note_files,
)
from text_utils import normalize_text


WEBSITES = {
    "youtube": "https://www.youtube.com",
    "google": "https://www.google.com",
    "chatgpt": "https://chatgpt.com",
}

OPEN_COMMANDS = ["otworz", "uruchom", "odpal", "wlacz", "open"]
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
APP_CATEGORIES_PATH = get_base_path() / "app_categories.json"
NOTES_PATH = get_base_path() / "notes"
NOTE_LIST_PATTERNS = [
    "jakie mam notatki",
    "jakie mam zapisane notatki",
    "pokaz notatki",
    "pokaz moje notatki",
    "pokaz moje zapisane notatki",
    "lista notatek",
    "wyswietl notatki",
]
NOTE_INTENT_WORDS = [
    "notes",
    "notatki",
    "notatke",
    "notatka",
    "zanotuj",
    "zapisz mi",
    "zapisz notatke",
    "dodaj notatke",
]
NOTE_COMMANDS = [
    "zrob notatke",
    "zapisz notatke",
    "zapisz prosze notatke",
    "zapisal notatke",
    "dodaj notatke",
    "zanotuj",
    "zapisz mi",
    "zapisz to",
    "utworz notatke",
]
NOTE_PREFIXES = [
    "zrób notatkę",
    "zrob notatke",
    "zapisz proszę notatkę",
    "zapisz prosze notatke",
    "zapisz notatkę",
    "zapisz notatke",
    "zapisał notatkę",
    "zapisal notatke",
    "dodaj notatkę",
    "dodaj notatke",
    "utwórz notatkę",
    "utworz notatke",
    "zapisz mi",
    "zapisz to",
    "zanotuj",
]
NOTE_INTRO_PATTERN = re.compile(
    r"^\s*(hej\s+jarvis|ok\s+jarvis|jarvis|proszę\s+jarvis|prosze\s+jarvis|proszę|prosze|możesz|mozesz)"
    r"[\s,:-]+",
    flags=re.IGNORECASE,
)


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


def parse_note_command(text):
    if not isinstance(text, str):
        return None

    command_text, separator, content = text.partition(":")
    if separator:
        command = normalize_text(command_text)
        if not is_note_command_text(command):
            return None

        title, note_content, has_title = parse_note_details(clean_note_content(content))
        return {
            "action": "create_note",
            "title": title,
            "content": note_content,
            "needs_title": not has_title and bool(note_content),
        }

    stripped_text = strip_note_intro(text.strip())
    lowered_text = stripped_text.lower()
    for prefix in sorted(NOTE_PREFIXES, key=len, reverse=True):
        matched_content = match_note_prefix(stripped_text, lowered_text, prefix)
        if matched_content is None:
            continue

        if not matched_content:
            title, note_content, has_title = parse_note_details("")
            return {
                "action": "create_note",
                "title": title,
                "content": note_content,
                "needs_title": not has_title and bool(note_content),
            }

        title, note_content, has_title = parse_note_details(clean_note_content(matched_content))
        return {
            "action": "create_note",
            "title": title,
            "content": note_content,
            "needs_title": not has_title and bool(note_content),
        }

    return None


def parse_note_list_command(text):
    normalized_text = normalize_text(strip_note_intro(text))
    if any(pattern in normalized_text for pattern in NOTE_LIST_PATTERNS):
        return {"action": "list_notes"}

    if contains_phrase(normalized_text, "notatki") and any(
        contains_phrase(normalized_text, command)
        for command in ["pokaz", "wyswietl", "lista", "jakie", "mam", "zapisane"]
    ):
        return {"action": "list_notes"}

    return None


def has_note_intent(text):
    normalized_text = normalize_text(strip_note_intro(text))
    if parse_note_command(text) or parse_note_list_command(text):
        return True

    return any(contains_phrase(normalized_text, word) for word in NOTE_INTENT_WORDS)


def match_note_prefix(original_text, lowered_text, prefix):
    if lowered_text == prefix:
        return ""

    if not lowered_text.startswith(prefix):
        return None

    content = original_text[len(prefix) :]
    if not content or content[0].isspace() or content[0] in ",:-":
        return content

    return None


def is_note_command_text(command):
    if command in NOTE_COMMANDS:
        return True

    return any(command.endswith(f" {note_command}") for note_command in NOTE_COMMANDS)


def strip_note_intro(text):
    previous_text = None
    cleaned_text = text
    while cleaned_text and cleaned_text != previous_text:
        previous_text = cleaned_text
        cleaned_text = NOTE_INTRO_PATTERN.sub("", cleaned_text, count=1).strip()

    return cleaned_text


def clean_note_content(content):
    content = content.strip(" ,:-")
    content = re.sub(r"^(że|ze)\s+", "", content, flags=re.IGNORECASE).strip()
    return content


def parse_note_details(content):
    content = content.strip()
    if not content:
        return "", "", False

    title_match = re.match(
        r"^\s*tytu[lł]\s+(?P<title>.+?)\s+tre[sś][cć]\s+(?P<content>.+)$",
        content,
        flags=re.IGNORECASE,
    )
    if title_match:
        title = title_match.group("title").strip(" :-")
        note_content = title_match.group("content").strip()
        return title or build_note_title(note_content), note_content, True

    if " - " in content:
        title, note_content = content.split(" - ", 1)
        title = title.strip()
        note_content = note_content.strip()
        if title and note_content:
            return title, note_content, True

    return "", content, False


def parse_local_action(text):
    note_action = parse_note_command(text)
    if note_action:
        return note_action

    note_list_action = parse_note_list_command(text)
    if note_list_action:
        return note_list_action

    text = normalize_text(text)

    spotify_action = parse_spotify_search(text)
    if spotify_action:
        return spotify_action

    if (contains_phrase(text, "notatki") or contains_phrase(text, "notes")) and not contains_phrase(text, "notatnik"):
        return {"action": "list_notes"}

    if has_command(text, OPEN_COMMANDS):
        website = find_target(text, WEBSITES.keys())
        if website:
            return {"action": "open_website", "target": website}

        app = find_target(text, load_apps().keys())
        if app:
            if app == "notepad" and has_note_intent(text):
                return {"action": "list_notes"}
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


def load_app_categories():
    if not APP_CATEGORIES_PATH.exists():
        return {}

    try:
        with APP_CATEGORIES_PATH.open("r", encoding="utf-8") as categories_file:
            categories = json.load(categories_file)
    except json.JSONDecodeError:
        return {}

    if not isinstance(categories, dict):
        return {}

    normalized_categories = {}
    for category, app_names in categories.items():
        if not isinstance(category, str) or not isinstance(app_names, list):
            continue

        normalized_names = [
            normalize_text(app_name)
            for app_name in app_names
            if isinstance(app_name, str) and app_name.strip()
        ]
        if normalized_names:
            normalized_categories[category] = normalized_names

    return normalized_categories


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

    try:
        result = subprocess.run(
            ["taskkill", "/IM", process_name, "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return "not_running"

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
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            creationflags=creationflags,
        )
    except OSError:
        return False

    if result.returncode != 0:
        return False

    return process_name.lower() in result.stdout.lower()


def spotify_search(query):
    query = normalize_text(query)
    if not query:
        return False

    os.startfile(f"spotify:search:{quote(query)}")
    return True


def create_note(content, title=None):
    return create_note_file(title or "", content)


def delete_note(note_path):
    return delete_note_file(note_path)


def load_notes():
    return list_note_files()


def list_notes():
    return list_note_files()
