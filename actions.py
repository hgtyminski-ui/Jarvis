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
WHATSAPP_PROCESS_NAMES = ["WhatsApp.exe", "WhatsApp", "WhatsAppApp.exe"]
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
NOTE_CONTROL_PHRASES = [
    "zapisz mi w notatkach",
    "zapisz w notatkach",
    "zapisz mi",
    "zapisz",
    "dodaj do notatek",
    "dodaj notatke",
    "dodaj notatkę",
    "zanotuj",
    "notatka",
    "w notatkach",
    "ze",
    "że",
]
NOTE_PREFIXES.append("dodaj do notatek")
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


def clean_note_content(content):
    return normalize_note_content(content)


def normalize_note_content(raw_text):
    content = str(raw_text or "").strip(" ,:-")
    content = re.sub(r"\s+", " ", content)
    content = strip_note_control_phrases(content)
    content = re.sub(r"\s+", " ", content).strip(" ,:-")
    if not content:
        return ""
    content = content[0].upper() + content[1:]
    if content[-1] not in ".!?":
        content += "."
    return content


def strip_note_control_phrases(content):
    cleaned = str(content or "").strip(" ,:-")
    changed = True
    while changed and cleaned:
        changed = False
        normalized = normalize_text(cleaned)
        for phrase in sorted(NOTE_CONTROL_PHRASES, key=len, reverse=True):
            normalized_phrase = normalize_text(phrase)
            if normalized == normalized_phrase:
                return ""
            if normalized.startswith(normalized_phrase + " "):
                cleaned = cleaned[len(phrase) :].strip(" ,:-")
                changed = True
                break
    return cleaned


def generate_note_title(content):
    normalized = normalize_text(content)
    if "mleko" in normalized or "kupic" in normalized or "zakupy" in normalized:
        return sanitize_note_title("Zakupy")
    if "imprez" in normalized:
        return sanitize_note_title("Impreza")
    if "lekarz" in normalized or "dentysta" in normalized:
        return sanitize_note_title("Lekarz" if "lekarz" in normalized else "Dentysta")
    if "spotkanie" in normalized:
        words = important_note_words(content)
        if len(words) >= 2:
            return sanitize_note_title(f"Spotkanie {words[1]}")
        return sanitize_note_title("Spotkanie")
    return sanitize_note_title(" ".join(important_note_words(content)[:2]))


def important_note_words(content):
    stop_words = {
        "mam",
        "masz",
        "trzeba",
        "musze",
        "muszę",
        "musisz",
        "jutro",
        "dzisiaj",
        "w",
        "na",
        "do",
        "ze",
        "że",
        "z",
        "o",
        "i",
    }
    words = re.findall(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż0-9]+", str(content or ""))
    important = []
    for word in words:
        normalized = normalize_text(word)
        if normalized in stop_words:
            continue
        important.append("Kuba" if normalized == "kuba" else word)
    return important


def sanitize_note_title(title):
    cleaned = str(title or "").strip().strip("\"'„”")
    cleaned = re.sub(r"[.!?]+$", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,:-")
    words = important_note_words(cleaned)[:2]
    if not words:
        return "Notatka"
    cleaned = " ".join(words)
    return cleaned[0].upper() + cleaned[1:]


def parse_note_details(content):
    content = normalize_note_content(content)
    if not content:
        return "", "", False

    title_match = re.match(
        r"^\s*tytu[lł]\s+(?P<title>.+?)\s+tre[sś][cć]\s+(?P<content>.+)$",
        content,
        flags=re.IGNORECASE,
    )
    if title_match:
        title = title_match.group("title").strip(" :-")
        note_content = normalize_note_content(title_match.group("content"))
        return title or generate_note_title(note_content), note_content, True

    if " - " in content:
        title, note_content = content.split(" - ", 1)
        title = title.strip()
        note_content = normalize_note_content(note_content)
        if title and note_content:
            return title, note_content, True

    return generate_note_title(content), content, bool(content)


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
    apps = load_apps_raw()
    normalized_apps = {}
    for name, entry in apps.items():
        if not isinstance(name, str):
            continue
        if isinstance(entry, dict) and entry.get("hidden") is True:
            continue

        command = app_command_from_entry(entry)
        if command:
            normalized_apps[str(name).lower()] = command

    return normalized_apps


def load_apps_raw():
    if not APPS_PATH.exists():
        return {}

    try:
        with APPS_PATH.open("r", encoding="utf-8") as apps_file:
            apps = json.load(apps_file)
    except json.JSONDecodeError:
        return {}

    if not isinstance(apps, dict):
        return {}

    return apps


def app_command_from_entry(entry):
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, dict):
        return ""
    return str(entry.get("command") or entry.get("launch_path") or entry.get("path") or entry.get("uri") or "").strip()


def app_process_from_entry(entry):
    if isinstance(entry, dict):
        process_name = str(entry.get("process") or "").strip()
        if process_name:
            return process_name

        for field in ["target_path", "path", "launch_path"]:
            value = str(entry.get(field) or "")
            if Path(value).suffix.lower() == ".exe":
                return Path(value).name
    elif isinstance(entry, str) and Path(entry).suffix.lower() == ".exe":
        return Path(entry).name

    return ""


def app_label_from_entry(entry, fallback):
    if isinstance(entry, dict):
        label = str(entry.get("label") or "").strip()
        if label:
            return label
    return str(fallback)


def resolve_app_key(target, apps):
    if target in apps:
        return target

    underscore_target = target.replace(" ", "_")
    if underscore_target in apps:
        return underscore_target

    space_target = target.replace("_", " ")
    if space_target in apps:
        return space_target

    return target


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
    raw_apps = load_apps_raw()
    apps = load_apps()
    target = resolve_app_key(target, apps)
    raw_entry = raw_apps.get(resolve_app_key(target, raw_apps))
    command = apps.get(target)

    if not command:
        return "unknown"

    if isinstance(raw_entry, dict) and raw_entry.get("type") == "command":
        arguments = str(raw_entry.get("arguments") or "").strip()
        full_command = f"{command} {arguments}".strip()
        subprocess.Popen(
            full_command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True,
        )
        return "opened"

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
    if target == "whatsapp":
        return close_whatsapp()

    processes = load_processes()
    process_name = processes.get(target)
    if not process_name:
        raw_apps = load_apps_raw()
        target = resolve_app_key(target, raw_apps)
        process_name = app_process_from_entry(raw_apps.get(target))

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


def taskkill_process(process_name):
    try:
        result = subprocess.run(
            ["taskkill", "/IM", process_name, "/F"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        return False

    return result.returncode == 0


def close_processes_by_window_or_name(pattern):
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    powershell_command = (
        "$pattern = '*{0}*'; "
        "$targets = Get-Process | Where-Object "
        "{{ $_.ProcessName -like $pattern -or $_.MainWindowTitle -like $pattern }}; "
        "if (-not $targets) {{ exit 1 }}; "
        "$targets | Stop-Process -Force; exit 0"
    ).format(pattern.replace("'", "''"))

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", powershell_command],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    except OSError:
        return False

    return result.returncode == 0


def close_whatsapp():
    closed = False
    for process_name in WHATSAPP_PROCESS_NAMES:
        if taskkill_process(process_name):
            closed = True

    if close_processes_by_window_or_name("WhatsApp"):
        closed = True

    return "closed" if closed else "not_running"


def is_app_running(target):
    target = resolve_alias(target)
    if target == "whatsapp":
        return is_whatsapp_running()

    processes = load_processes()
    process_name = processes.get(target)
    if not process_name:
        raw_apps = load_apps_raw()
        target = resolve_app_key(target, raw_apps)
        process_name = app_process_from_entry(raw_apps.get(target))

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


def is_whatsapp_running():
    return any(is_process_running(process_name) for process_name in WHATSAPP_PROCESS_NAMES)


def is_process_running(process_name):
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


def create_note(content, title=None, user_id=None):
    return create_note_file(title or "", content, user_id=user_id)


def delete_note(note_path, user_id=None):
    return delete_note_file(note_path, user_id=user_id)


def load_notes(user_id=None):
    return list_note_files(user_id=user_id)


def list_notes(user_id=None):
    return list_note_files(user_id=user_id)
