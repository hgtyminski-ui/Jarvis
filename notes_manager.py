import json
import re
from datetime import datetime
from pathlib import Path

from path_utils import get_base_path
from text_utils import normalize_text


NOTES_PATH = get_base_path() / "notes"
DEFAULT_USER_ID = "hubert"


def build_note_title(content):
    words = str(content).strip().split()
    if not words:
        return ""
    return " ".join(words[:5])


def safe_note_slug(title):
    slug = normalize_text(title)
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or "notatka"


def create_note(title, content, user_id=None):
    if not isinstance(content, str) or not content.strip():
        return "missing_content"

    NOTES_PATH.mkdir(exist_ok=True)
    note_content = content.strip()
    note_title = title.strip() if isinstance(title, str) and title.strip() else build_note_title(note_content)
    created_at = datetime.now()
    timestamp = created_at.strftime("%Y-%m-%d_%H-%M")
    slug = safe_note_slug(note_title)
    note_path = NOTES_PATH / f"{timestamp}_{slug}.json"

    if note_path.exists():
        timestamp = created_at.strftime("%Y-%m-%d_%H-%M-%S")
        note_path = NOTES_PATH / f"{timestamp}_{slug}.json"

    note = {
        "title": note_title,
        "content": note_content,
        "created_at": created_at.strftime("%Y-%m-%d %H:%M:%S"),
    }
    if user_id:
        note["user_id"] = str(user_id)

    note_path.write_text(json.dumps(note, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return "saved"


def list_notes(user_id=None):
    NOTES_PATH.mkdir(exist_ok=True)
    notes = []
    requested_user_id = str(user_id) if user_id else None

    for note_path in NOTES_PATH.glob("*.json"):
        try:
            data = json.loads(note_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(data, dict):
            continue

        note_user_id = str(data.get("user_id") or DEFAULT_USER_ID)
        if requested_user_id and note_user_id != requested_user_id:
            continue

        notes.append(
            {
                "title": str(data.get("title") or "Bez tytulu"),
                "content": str(data.get("content") or ""),
                "created_at": str(data.get("created_at") or ""),
                "path": str(note_path),
                "legacy": False,
                "user_id": note_user_id,
            }
        )

    for note_path in NOTES_PATH.glob("*.txt"):
        if requested_user_id and requested_user_id != DEFAULT_USER_ID:
            continue

        try:
            modified_at = datetime.fromtimestamp(note_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        except OSError:
            modified_at = ""

        try:
            legacy_content = note_path.read_text(encoding="utf-8")
        except OSError:
            legacy_content = ""

        notes.append(
            {
                "title": "Stara notatka",
                "content": legacy_content,
                "created_at": modified_at,
                "path": str(note_path),
                "legacy": True,
                "user_id": DEFAULT_USER_ID,
            }
        )

    return sorted(notes, key=lambda note: note.get("created_at", ""), reverse=True)


def delete_note(note_id_or_filepath, user_id=None):
    try:
        resolved_notes_path = NOTES_PATH.resolve()
        resolved_note_path = Path(note_id_or_filepath).resolve()
    except (OSError, TypeError, ValueError):
        return "error"

    if resolved_note_path.parent != resolved_notes_path:
        return "error"

    if resolved_note_path.suffix.lower() not in [".json", ".txt"]:
        return "error"

    requested_user_id = str(user_id) if user_id else None
    if requested_user_id and resolved_note_path.suffix.lower() == ".json":
        try:
            data = json.loads(resolved_note_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return "error"
        note_user_id = str(data.get("user_id") or DEFAULT_USER_ID) if isinstance(data, dict) else DEFAULT_USER_ID
        if note_user_id != requested_user_id:
            return "missing"
    elif requested_user_id and requested_user_id != DEFAULT_USER_ID:
        return "missing"

    try:
        resolved_note_path.unlink()
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "error"

    return "deleted"
