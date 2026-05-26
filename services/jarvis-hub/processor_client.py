import os

import requests
from dotenv import load_dotenv


load_dotenv()

DEFAULT_PROCESSOR_URL = "http://127.0.0.1:8001"
PROCESSOR_TIMEOUT_SECONDS = 8


def processor_url():
    return os.getenv("JARVIS_PROCESSOR_URL", DEFAULT_PROCESSOR_URL).rstrip("/")


def interpret_text(text):
    try:
        response = requests.post(
            f"{processor_url()}/interpret",
            json={"text": text},
            timeout=PROCESSOR_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        return {
            "ok": False,
            "error": f"Processor niedostępny: {e}",
            "command": None,
        }

    command = data.get("command") if isinstance(data, dict) else None
    if not isinstance(command, dict):
        return {
            "ok": False,
            "error": "Processor zwrócił niepoprawną komendę.",
            "command": None,
        }

    return {
        "ok": True,
        "error": None,
        "command": command,
    }
