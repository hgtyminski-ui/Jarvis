import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path


DATA_DIR = Path(__file__).resolve().parent / "data"
NOTES_PATH = DATA_DIR / "notes.json"
_lock = threading.Lock()


def _ensure_store():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not NOTES_PATH.exists():
        NOTES_PATH.write_text("[]\n", encoding="utf-8")


def _read_notes_unlocked():
    _ensure_store()
    try:
        data = json.loads(NOTES_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        data = []
    if not isinstance(data, list):
        return []
    return [note for note in data if isinstance(note, dict)]


def _write_notes_unlocked(notes):
    _ensure_store()
    NOTES_PATH.write_text(
        json.dumps(notes, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def list_notes():
    with _lock:
        notes = _read_notes_unlocked()
    return sorted(notes, key=lambda note: str(note.get("created_at") or ""), reverse=True)


def get_note(note_id):
    with _lock:
        for note in _read_notes_unlocked():
            if str(note.get("id")) == str(note_id):
                return note
    return None


def create_note(title, content):
    note = {
        "id": uuid.uuid4().hex,
        "title": str(title).strip(),
        "content": str(content or "").strip(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        notes = _read_notes_unlocked()
        notes.append(note)
        _write_notes_unlocked(notes)
    return note


def delete_note(note_id):
    with _lock:
        notes = _read_notes_unlocked()
        filtered = [note for note in notes if str(note.get("id")) != str(note_id)]
        if len(filtered) == len(notes):
            return False
        _write_notes_unlocked(filtered)
    return True
