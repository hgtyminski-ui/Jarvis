import os

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from agent_manager import AgentManager
from processor_client import interpret_text


load_dotenv()

app = FastAPI(title="Jarvis Hub")
agents = AgentManager()


class ProcessTextRequest(BaseModel):
    text: str
    device_id: str


def auth_token():
    return os.getenv("AUTH_TOKEN", "dev-token")


def verify_token(x_jarvis_token: str | None = Header(default=None)):
    if x_jarvis_token != auth_token():
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/agents")
def list_agents(_authorized: None = Depends(verify_token)):
    return {"agents": agents.list_agents()}


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


@app.post("/process-text")
async def process_text(
    request: ProcessTextRequest,
    _authorized: None = Depends(verify_token),
):
    result = interpret_text(request.text)
    if not result["ok"]:
        return {
            "status": "error",
            "response": result["error"],
            "device_id": request.device_id,
        }

    command = result["command"]
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
