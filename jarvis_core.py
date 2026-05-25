import json
from dataclasses import dataclass

from actions import (
    close_app,
    create_note,
    list_notes,
    open_app,
    open_website,
    parse_ai_json,
    parse_local_action,
    resolve_alias,
    spotify_search,
)
from ai_client import check_connection, create_client, get_ai_response
from config import load_config
from memory import add_assistant_message, add_user_message, clear_messages, create_messages
from text_utils import normalize_text


@dataclass
class JarvisResult:
    response: str
    should_exit: bool = False
    tts_text: str | None = None


class JarvisRuntime:
    def __init__(self, config=None, client=None, messages=None, pending_note=None):
        self.config = config if config is not None else load_config()
        self.assistant_name = self.config["assistant_name"]
        self.client = client if client is not None else create_client(self.config)
        self.messages = messages if messages is not None else create_messages(self.config)
        self.pending_note = pending_note if pending_note is not None else {}

    def check_lm_studio(self):
        check_connection(self.client, self.config)

    def status(self):
        try:
            self.check_lm_studio()
            lm_studio = "online"
        except Exception:
            lm_studio = "offline"

        return {
            "status": "online",
            "lm_studio": lm_studio,
            "model": self.config.get("model", "local-model"),
        }

    def process(self, user_input):
        return process_user_text(
            user_input,
            self.assistant_name,
            self.client,
            self.config,
            self.messages,
            self.pending_note,
        )


def format_with_name(assistant_name, response):
    if not response:
        return f"{assistant_name}:"
    return f"{assistant_name}: {response}"


def show_help_text():
    return "\n".join(
        [
            "Dostepne komendy:",
            "/help - pokazuje dostepne komendy",
            "/exit - konczy program",
            "/status - sprawdza polaczenie z LM Studio",
            "/clear - czysci historie rozmowy z RAM",
            "/listen - nagrywa krotka wiadomosc z mikrofonu",
            "/close <aplikacja> - zamyka aplikacje z processes.json",
            "zanotuj [tekst] / zapisz notatke [tekst] - zapisuje notatke w folderze notes",
            "pokaz notatki / lista notatek - pokazuje zapisane notatki",
        ]
    )


def handle_local_command(command, assistant_name, client, config, messages):
    if command == "/help":
        return JarvisResult(show_help_text())

    if command == "/exit":
        return JarvisResult(
            format_with_name(assistant_name, "Wylaczam sie. Do zobaczenia!"),
            should_exit=True,
        )

    if command == "/status":
        try:
            check_connection(client, config)
            return JarvisResult("Status: polaczenie z LM Studio dziala.")
        except Exception as e:
            return JarvisResult(f"Status: brak polaczenia z LM Studio.\nBlad: {e}")

    if command == "/clear":
        clear_messages(messages, config)
        return JarvisResult("Historia rozmowy w RAM zostala wyczyszczona.")

    local_action = parse_local_action(command.lstrip("/"))
    if local_action:
        return handle_ai_answer(json.dumps(local_action), assistant_name, config)

    return JarvisResult("Nieznana komenda lokalna. Wpisz /help, aby zobaczyc dostepne komendy.")


def handle_ai_answer(answer, assistant_name, config):
    data = parse_ai_json(answer)
    action = data.get("action")

    if action == "chat":
        response = data.get("response", "")
        return JarvisResult(format_with_name(assistant_name, response), tts_text=response)

    if action == "open_website":
        target = resolve_alias(data.get("target", ""))
        if open_website(target):
            return JarvisResult(format_with_name(assistant_name, f"Otwieram strone: {target}"))
        return JarvisResult(format_with_name(assistant_name, "Nie obsluguje tej strony."))

    if action == "open_app":
        target = resolve_alias(data.get("target", ""))

        try:
            result = open_app(target)
        except Exception as e:
            return JarvisResult(
                f"{format_with_name(assistant_name, f'Nie udalo sie uruchomic aplikacji: {target}')}\nBlad: {e}"
            )

        if result == "opened":
            return JarvisResult(format_with_name(assistant_name, f"Otwieram aplikacje: {target}"))
        return JarvisResult(format_with_name(assistant_name, f"Nie znam aplikacji: {target}. Dodaj ja do apps.json."))

    if action == "close_app":
        target = resolve_alias(data.get("target", ""))

        try:
            result = close_app(target)
        except Exception as e:
            return JarvisResult(
                f"{format_with_name(assistant_name, f'Nie udalo sie zamknac aplikacji: {target}')}\nBlad: {e}"
            )

        if result == "closed":
            return JarvisResult(format_with_name(assistant_name, f"Zamykam {target}."))
        if result == "not_running":
            return JarvisResult(format_with_name(assistant_name, f"Nie znalazlem uruchomionego procesu dla: {target}."))
        return JarvisResult(format_with_name(assistant_name, f"Nie znam aplikacji: {target}. Dodaj ja do processes.json."))

    if action == "spotify_search":
        query = data.get("query", "")

        if spotify_search(query):
            return JarvisResult(format_with_name(assistant_name, f"Szukam w Spotify: {query}"))
        return JarvisResult(format_with_name(assistant_name, "Nie podano czego szukac w Spotify."))

    if action == "list_notes":
        return JarvisResult(format_notes_response(assistant_name))

    if action == "create_note":
        content = data.get("content", "")
        title = data.get("title", "")

        try:
            result = create_note(content, title)
        except Exception as e:
            return JarvisResult(f"{format_with_name(assistant_name, 'Nie udalo sie zapisac notatki.')}\nBlad: {e}")

        if result == "saved":
            return JarvisResult(format_with_name(assistant_name, "Notatka zapisana."))
        return JarvisResult(format_with_name(assistant_name, "Brakuje tresci notatki."))

    return JarvisResult(format_with_name(assistant_name, "Nie rozumiem akcji zwroconej przez AI."))


def format_notes_response(assistant_name):
    notes = list_notes()
    if not notes:
        return format_with_name(assistant_name, "Nie masz zapisanych notatek.")

    lines = [format_with_name(assistant_name, "Zapisane notatki:")]
    for note in notes:
        title = str(note.get("title") or "Bez tytulu")
        created_at = str(note.get("created_at") or "brak daty")
        lines.append(f"- {title} - {created_at}")

    return "\n".join(lines)


def process_user_text(user_input, assistant_name, client, config, messages, pending_note=None):
    if user_input.startswith("/"):
        return handle_local_command(
            user_input.strip().lower(),
            assistant_name,
            client,
            config,
            messages,
        )

    normalized_user_input = normalize_text(user_input)

    if pending_note is not None and pending_note.get("content"):
        if normalized_user_input in ["anuluj", "cancel"]:
            pending_note.clear()
            response = "Anulowano notatke."
            return JarvisResult(format_with_name(assistant_name, response), tts_text=response)

        title = user_input.strip()
        if not title:
            response = "Jaki ma byc tytul notatki?"
            return JarvisResult(format_with_name(assistant_name, response), tts_text=response)

        try:
            result = create_note(pending_note["content"], title)
        except Exception as e:
            pending_note.clear()
            return JarvisResult(f"{format_with_name(assistant_name, 'Nie udalo sie zapisac notatki.')}\nBlad: {e}")

        pending_note.clear()
        if result == "saved":
            response = "Notatka zapisana."
            return JarvisResult(format_with_name(assistant_name, response), tts_text=response)

        return JarvisResult(format_with_name(assistant_name, "Brakuje tresci notatki."))

    normalized_exit_commands = [
        normalize_text(command) for command in config["exit_commands"]
    ]

    if normalized_user_input in normalized_exit_commands:
        return JarvisResult(
            format_with_name(assistant_name, "Wylaczam sie. Do zobaczenia!"),
            should_exit=True,
        )

    local_action = parse_local_action(user_input)
    if local_action:
        if local_action.get("action") == "create_note" and local_action.get("needs_title"):
            content = local_action.get("content", "").strip()
            if not content:
                return JarvisResult(format_with_name(assistant_name, "Brakuje tresci notatki."))

            if pending_note is not None:
                pending_note["content"] = content
            question = "Jaki ma byc tytul notatki?"
            return JarvisResult(format_with_name(assistant_name, question), tts_text=question)

        return handle_ai_answer(json.dumps(local_action), assistant_name, config)

    add_user_message(messages, normalized_user_input)

    try:
        answer = get_ai_response(client, messages, config)
        if not answer or not answer.strip():
            response = "Nie otrzymalem odpowiedzi."
            add_assistant_message(messages, response)
            return JarvisResult(format_with_name(assistant_name, response), tts_text=response)

        result = handle_ai_answer(answer, assistant_name, config)
        add_assistant_message(messages, answer)
        return result
    except Exception as e:
        return JarvisResult(f"Blad: {e}")
