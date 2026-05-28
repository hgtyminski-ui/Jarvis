import json
import os
import re
import unicodedata

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

SUPPORTED_ACTIONS = {
    "open_app",
    "close_app",
    "volume_up",
    "volume_down",
    "volume_mute",
    "system_sleep",
    "system_shutdown",
    "create_note",
    "create_reminder",
    "chat",
    "unknown",
}

DEFAULT_COMMAND = {"action": "unknown", "app": None, "parameters": {}}
GREETING_COMMAND = {
    "action": "chat",
    "app": None,
    "parameters": {},
    "response": "Cześć. Jak mogę pomóc?",
}
LOCAL_GREETINGS = {"hej", "siema", "czesc"}
LOCAL_APP_COMMANDS = {
    ("otworz", "spotify"): {"action": "open_app", "app": "spotify", "parameters": {}},
    ("zamknij", "spotify"): {"action": "close_app", "app": "spotify", "parameters": {}},
    ("otworz", "discord"): {"action": "open_app", "app": "discord", "parameters": {}},
    ("zamknij", "discord"): {"action": "close_app", "app": "discord", "parameters": {}},
    ("zamknij", "whatsapp"): {"action": "close_app", "app": "whatsapp", "parameters": {}},
    ("zamknij", "whatsappa"): {"action": "close_app", "app": "whatsapp", "parameters": {}},
    ("close", "whatsapp"): {"action": "close_app", "app": "whatsapp", "parameters": {}},
}
NOTE_PREFIXES = [
    "zapisz notatke",
    "dodaj notatke",
    "zanotuj",
    "zapisz mi",
    "utworz notatke",
    "zapisz",
]
REMINDER_PREFIXES = [
    "przypomnij mi",
    "ustaw przypomnienie",
    "przypomnienie",
]


def normalize_text(text):
    lowered = str(text or "").strip().lower()
    without_accents = unicodedata.normalize("NFKD", lowered)
    without_accents = "".join(char for char in without_accents if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents)


def create_note_command(title, content, needs_title):
    normalized_content = normalize_note_content(content)
    parameters = {
        "title": title if title else None,
        "content": normalized_content,
        "raw_content": str(content or "").strip(),
        "needs_title": needs_title,
    }
    response = "Podaj tytuł notatki." if needs_title else f"Zapisałem notatkę: {title}"
    return {
        "action": "create_note",
        "app": None,
        "parameters": parameters,
        "response": response,
    }


def strip_note_command_words(content):
    cleaned = str(content or "").strip(" :-,\t\r\n")
    command_words = [
        "że",
        "ze",
        "mi",
        "proszę",
        "prosze",
        "notatkę",
        "notatke",
    ]

    changed = True
    while changed and cleaned:
        changed = False
        for word in command_words:
            pattern = rf"^{re.escape(word)}(?:\s+|$)"
            updated = re.sub(pattern, "", cleaned, count=1, flags=re.IGNORECASE).strip(" :-,\t\r\n")
            if updated != cleaned:
                cleaned = updated
                changed = True
                break
    return cleaned


def sentence_case(text):
    text = re.sub(r"\s+", " ", str(text or "").strip())
    if not text:
        return ""

    replacements = {
        "dentyste": "dentystę",
    }
    words = [replacements.get(word, word) for word in text.split(" ")]
    text = " ".join(words)
    text = text[0].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


def normalize_note_content(raw_text):
    cleaned = strip_note_command_words(raw_text)
    locally_normalized = sentence_case(cleaned)
    if not locally_normalized:
        return ""

    if should_rewrite_note_with_llm(cleaned):
        return rewrite_note_content_with_llm(cleaned) or locally_normalized

    return locally_normalized


def should_rewrite_note_with_llm(content):
    normalized = normalize_text(content)
    if len(normalized.split()) > 18:
        return True
    return any(marker in normalized for marker in [" i jeszcze ", " a potem ", " oraz "])


def rewrite_note_content_with_llm(content):
    try:
        response = llm_client().chat.completions.create(
            model=llm_model(),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Przepisz treść notatki po polsku w naturalnej formie. "
                        "Nie dodawaj nowych informacji. Nie rób z tego przypomnienia. "
                        "Zwróć tylko czysty tekst notatki, bez JSON-a i bez komentarzy."
                    ),
                },
                {"role": "user", "content": str(content or "")},
            ],
            temperature=0,
        )
        rewritten = response.choices[0].message.content.strip()
    except Exception:
        return ""

    if not rewritten:
        return ""
    if "\n" in rewritten:
        rewritten = rewritten.splitlines()[0].strip()
    return sentence_case(strip_note_command_words(rewritten))


def parse_note_payload(content):
    content = str(content or "").strip(" :-,")
    if not content:
        return "", "", True

    title_match = re.match(
        r"^\s*tytu[lł]\s+(?P<title>.+?)\s+tre[sś][cć]\s+(?P<content>.+)$",
        content,
        flags=re.IGNORECASE,
    )
    if title_match:
        title = title_match.group("title").strip(" :-")
        note_content = title_match.group("content").strip()
        if title and note_content:
            return title, note_content, False

    if ":" in content:
        title, note_content = content.split(":", 1)
        title = title.strip()
        note_content = note_content.strip()
        if title and note_content:
            return title, note_content, False

    if " - " in content:
        title, note_content = content.split(" - ", 1)
        title = title.strip()
        note_content = note_content.strip()
        if title and note_content:
            return title, note_content, False

    return "", content, True


def local_parse_note(text):
    raw_text = str(text or "").strip()
    normalized = normalize_text(raw_text)

    if any(normalized.startswith(prefix) for prefix in REMINDER_PREFIXES):
        return None

    for prefix in sorted(NOTE_PREFIXES, key=len, reverse=True):
        if normalized == prefix:
            title, content, needs_title = parse_note_payload("")
            return create_note_command(title, content, needs_title)
        if normalized.startswith(prefix + " "):
            content = raw_text[len(prefix) :].strip()
            title, note_content, needs_title = parse_note_payload(content)
            return create_note_command(title, note_content, needs_title)

    return None


def local_parse(text):
    normalized = normalize_text(text)
    if normalized in LOCAL_GREETINGS:
        return GREETING_COMMAND.copy()

    note_command = local_parse_note(text)
    if note_command:
        return note_command

    for (verb, app_name), command in LOCAL_APP_COMMANDS.items():
        if normalized == f"{verb} {app_name}":
            return command.copy()
    return None


def llm_client():
    return OpenAI(
        base_url=os.getenv("LLM_BASE_URL", "http://127.0.0.1:1233/v1"),
        api_key=os.getenv("LLM_API_KEY", "lm-studio"),
    )


def llm_model():
    return os.getenv("LLM_MODEL", "local-model")


def parse_llm_json(content):
    try:
        data = json.loads(content)
    except (TypeError, json.JSONDecodeError):
        return DEFAULT_COMMAND.copy()

    command = data.get("command") if isinstance(data, dict) else None
    if not isinstance(command, dict):
        return DEFAULT_COMMAND.copy()

    action = command.get("action")
    if action not in SUPPORTED_ACTIONS:
        return DEFAULT_COMMAND.copy()

    app_name = command.get("app")
    parameters = command.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}

    parsed_command = {
        "action": action,
        "app": app_name if app_name is None or isinstance(app_name, str) else str(app_name),
        "parameters": parameters,
    }

    if action in {"chat", "create_note", "create_reminder"}:
        response = (
            command.get("response")
            or parameters.get("response")
            or parameters.get("message")
            or command.get("message")
            or ""
        )
        parsed_command["response"] = str(response)

    return parsed_command


def interpret_with_llm(text):
    system_prompt = (
        "You are Jarvis Processor. The user speaks Polish. Return only valid JSON, no markdown. "
        "Odpowiadaj zawsze po polsku. "
        "Nie używaj duńskiego, angielskiego ani innych języków, chyba że użytkownik wyraźnie o to poprosi. "
        "Dla zwykłej rozmowy zwracaj action='chat' i response po polsku. "
        "Notatka nie jest przypomnieniem. Frazy zawierające notatka, notatkę, notatke, zanotuj, zapisz mi "
        "zwracaj jako action='create_note', nigdy jako reminder. "
        "Dla create_note przepisz parameters.content jako krótką, naturalną notatkę po polsku, "
        "zachowaj surową treść w parameters.raw_content i nie dodawaj nowych faktów. "
        "Reminder/przypomnienie zwracaj tylko dla fraz typu przypomnij mi, ustaw przypomnienie, przypomnienie. "
        "Schema: {\"command\":{\"action\":\"open_app|close_app|volume_up|volume_down|"
        "volume_mute|system_sleep|system_shutdown|create_note|create_reminder|chat|unknown\",\"app\":string|null,"
        "\"parameters\":{},\"response\":string}}. For action chat, always include "
        "command.response with the assistant reply in Polish. If unsure, use action unknown."
    )

    response = llm_client().chat.completions.create(
        model=llm_model(),
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": str(text or "")},
        ],
        temperature=0,
    )
    content = response.choices[0].message.content
    return parse_llm_json(content)


def interpret_text(text):
    local_command = local_parse(text)
    if local_command:
        return local_command

    try:
        return interpret_with_llm(text)
    except Exception:
        return DEFAULT_COMMAND.copy()
