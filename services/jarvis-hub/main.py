import os
import re
import unicodedata

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent_manager import AgentManager
from notes_store import create_note, delete_note, get_note, list_notes
from processor_client import interpret_text


load_dotenv()

app = FastAPI(title="Jarvis Hub")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
agents = AgentManager()


class ProcessTextRequest(BaseModel):
    text: str
    device_id: str


class NoteRequest(BaseModel):
    title: str
    content: str


class AgentCommandRequest(BaseModel):
    device_id: str | None = None
    command: dict | None = None


def auth_token():
    return os.getenv("AUTH_TOKEN", "dev-token")


def verify_token(x_jarvis_token: str | None = Header(default=None)):
    if x_jarvis_token != auth_token():
        raise HTTPException(status_code=401, detail="Unauthorized")


def command_response(command: dict):
    parameters = command.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}
    response = (
        command.get("response")
        or parameters.get("response")
        or parameters.get("message")
        or command.get("message")
    )
    return str(response) if response else ""


def command_parameters(command: dict):
    parameters = command.get("parameters")
    return parameters if isinstance(parameters, dict) else {}


def note_payload_from_command(command: dict):
    parameters = command_parameters(command)
    title = (
        command.get("title")
        or command.get("name")
        or parameters.get("title")
        or parameters.get("name")
    )
    content = (
        command.get("content")
        or command.get("text")
        or parameters.get("content")
        or parameters.get("text")
        or parameters.get("body")
        or parameters.get("message")
        or ""
    )
    return str(title or "").strip(), str(content or "").strip()


def command_needs_note_title(command: dict):
    parameters = command_parameters(command)
    needs_title = parameters.get("needs_title")
    if isinstance(needs_title, bool):
        return needs_title
    if isinstance(needs_title, str):
        return needs_title.strip().lower() in {"1", "true", "yes", "tak"}
    return False


def normalize_text(text):
    lowered = str(text or "").strip().lower()
    without_accents = unicodedata.normalize("NFKD", lowered)
    without_accents = "".join(char for char in without_accents if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", without_accents)


def parse_note_text(text):
    raw_text = str(text or "").strip()
    normalized = normalize_text(raw_text)
    prefixes = [
        "zapisz notatke",
        "dodaj notatke",
        "zapisz notatkę",
        "dodaj notatkę",
    ]

    matched_prefix = None
    for prefix in prefixes:
        normalized_prefix = normalize_text(prefix)
        if normalized == normalized_prefix:
            matched_prefix = prefix
            content = ""
            break
        if normalized.startswith(normalized_prefix + " "):
            matched_prefix = prefix
            content = raw_text[len(prefix) :].strip(" :-,")
            break
    else:
        return None

    title = ""
    note_content = content.strip()
    title_match = re.match(
        r"^\s*tytu[lł]\s+(?P<title>.+?)\s+tre[sś][cć]\s+(?P<content>.+)$",
        note_content,
        flags=re.IGNORECASE,
    )
    if title_match:
        title = title_match.group("title").strip(" :-")
        note_content = title_match.group("content").strip()
    elif " - " in note_content:
        possible_title, possible_content = note_content.split(" - ", 1)
        if possible_title.strip() and possible_content.strip():
            title = possible_title.strip()
            note_content = possible_content.strip()

    return {
        "title": title,
        "content": note_content,
        "matched_prefix": matched_prefix,
    }


def need_note_title_response(content, device_id):
    return {
        "status": "need_input",
        "response": "Podaj tytuł notatki.",
        "missing": "title",
        "draft": {
            "content": content,
        },
        "device_id": device_id,
    }


def save_note_response(title, content, device_id, command=None):
    note = create_note(title, content)
    response = {
        "status": "ok",
        "response": f"Zapisałem notatkę: {note['title']}",
        "device_id": device_id,
        "note": note,
    }
    if command is not None:
        response["command"] = {
            **command,
            "note": note,
        }
    return response


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/agents")
def list_agents(_authorized: None = Depends(verify_token)):
    return {"agents": agents.list_agents()}


@app.get("/notes")
def notes_index(_authorized: None = Depends(verify_token)):
    return {"notes": list_notes()}


@app.post("/notes")
def notes_create(request: NoteRequest, _authorized: None = Depends(verify_token)):
    title = request.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")
    return create_note(title, request.content)


@app.get("/notes/{note_id}")
def notes_show(note_id: str, _authorized: None = Depends(verify_token)):
    note = get_note(note_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Nie znaleziono notatki.")
    return note


@app.delete("/notes/{note_id}")
def notes_delete(note_id: str, _authorized: None = Depends(verify_token)):
    if not delete_note(note_id):
        raise HTTPException(status_code=404, detail="Nie znaleziono notatki.")
    return {"status": "deleted"}


@app.websocket("/agent/connect/{device_id}")
async def connect_agent(websocket: WebSocket, device_id: str):
    if websocket.query_params.get("token") != auth_token():
        await websocket.close(code=1008)
        return

    await agents.connect(device_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        agents.disconnect(device_id)


@app.post("/agent/command")
async def send_agent_command(
    request: AgentCommandRequest,
    _authorized: None = Depends(verify_token),
):
    device_id = str(request.device_id or "").strip()
    if not device_id:
        raise HTTPException(status_code=400, detail="device_id is required")
    if not isinstance(request.command, dict) or not request.command:
        raise HTTPException(status_code=400, detail="command is required")

    sent = await agents.send_command(device_id, request.command)
    if not sent:
        raise HTTPException(status_code=404, detail="Agent not connected")

    return {"status": "sent"}


@app.post("/process-text")
async def process_text(
    request: ProcessTextRequest,
    _authorized: None = Depends(verify_token),
):
    local_note = parse_note_text(request.text)
    if local_note is not None:
        title = local_note["title"]
        content = local_note["content"]
        if not title:
            return need_note_title_response(content, request.device_id)
        return save_note_response(title, content, request.device_id)

    result = interpret_text(request.text)
    if not result["ok"]:
        return {
            "status": "error",
            "response": result["error"],
            "device_id": request.device_id,
        }

    command = result["command"]
    action = str(command.get("action") or "").strip().lower()

    if action in {"create_note", "note_create"}:
        title, content = note_payload_from_command(command)
        if command_needs_note_title(command) or not title:
            response = need_note_title_response(content, request.device_id)
            response["command"] = command
            return response
        return save_note_response(title, content, request.device_id, command)

    if action == "chat":
        response = command_response(command)
        return {
            "status": "ok",
            "response": response or "Brak tekstu odpowiedzi z Huba",
            "device_id": request.device_id,
            "command": command,
        }

    sent = await agents.send_command(request.device_id, command)
    if not sent:
        return {
            "status": "error",
            "response": f"Agent nie jest podłączony: {request.device_id}",
            "device_id": request.device_id,
            "command": command,
        }

    return {
        "status": "sent",
        "device_id": request.device_id,
        "command": command,
    }
