import json
from pathlib import Path


CONFIG_PATH = Path(__file__).with_name("config.json")
REQUIRED_SETTINGS = ["assistant_name", "base_url", "model", "temperature", "system_message"]


class ConfigError(Exception):
    pass


def load_config():
    if not CONFIG_PATH.exists():
        raise ConfigError(
            "Brak pliku config.json. Utwórz go w folderze projektu Jarvis."
        )

    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except json.JSONDecodeError as e:
        raise ConfigError(f"Plik config.json ma niepoprawny format JSON: {e}") from e

    if not isinstance(config, dict):
        raise ConfigError("Plik config.json musi zawierać obiekt JSON z ustawieniami.")

    missing_settings = [name for name in REQUIRED_SETTINGS if name not in config]
    if missing_settings:
        missing = ", ".join(missing_settings)
        raise ConfigError(f"Brak wymaganych ustawień w config.json: {missing}.")

    config.setdefault("api_key", "lm-studio")
    config.setdefault("exit_commands", ["exit", "quit", "wyjdź", "koniec", "zamknij"])
    config.setdefault("voice_enabled", True)
    config.setdefault("voice_id", 0)
    config.setdefault("voice_rate", 150)
    config.setdefault("voice_volume", 0.9)
    config.setdefault("tts_engine", "edge")
    config.setdefault("edge_voice", "pl-PL-MarekNeural")
    config.setdefault("edge_rate", "+0%")
    config.setdefault("edge_volume", "+0%")

    return config
