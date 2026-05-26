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
    "chat",
    "unknown",
}

DEFAULT_COMMAND = {"action": "unknown", "app": None, "parameters": {}}
LOCAL_APP_COMMANDS = {
    ("otworz", "spotify"): {"action": "open_app", "app": "spotify", "parameters": {}},
    ("zamknij", "spotify"): {"action": "close_app", "app": "spotify", "parameters": {}},
    ("otworz", "discord"): {"action": "open_app", "app": "discord", "parameters": {}},
    ("zamknij", "discord"): {"action": "close_app", "app": "discord", "parameters": {}},
}


def normalize_text(text):
    lowered = str(text or "").strip().lower()
    without_accents = unicodedata.normalize("NFKD", lowered)
    without_accents = "".join(char for char in without_accents if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents)


def local_parse(text):
    normalized = normalize_text(text)
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

    return {
        "action": action,
        "app": app_name if app_name is None or isinstance(app_name, str) else str(app_name),
        "parameters": parameters,
    }


def interpret_with_llm(text):
    system_prompt = (
        "You are Jarvis Processor. Return only valid JSON, no markdown. "
        "Schema: {\"command\":{\"action\":\"open_app|close_app|volume_up|volume_down|"
        "volume_mute|system_sleep|system_shutdown|chat|unknown\",\"app\":string|null,"
        "\"parameters\":{}}}. If unsure, use action unknown."
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
