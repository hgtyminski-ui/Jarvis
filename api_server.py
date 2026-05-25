from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from threading import Lock


app = FastAPI(title="Jarvis API")
runtime = None
runtime_lock = Lock()


class ChatRequest(BaseModel):
    message: str


class CommandRequest(BaseModel):
    command: str


def get_runtime():
    global runtime

    if runtime is None:
        from jarvis_core import JarvisRuntime

        runtime = JarvisRuntime()

    return runtime


def verify_token(x_jarvis_token: str | None = Header(default=None)):
    try:
        from config import load_config

        expected_token = load_config().get("api_token")
    except Exception:
        expected_token = None

    if not expected_token or x_jarvis_token != expected_token:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/status")
def get_status():
    try:
        with runtime_lock:
            return get_runtime().status()
    except Exception:
        return {
            "status": "online",
            "lm_studio": "offline",
            "model": "local-model",
        }


@app.post("/chat")
def chat(request: ChatRequest, _authorized: None = Depends(verify_token)):
    try:
        with runtime_lock:
            result = get_runtime().process(request.message)
        return {"response": result.response}
    except Exception as e:
        return {"response": f"Blad Jarvisa: {e}"}


@app.post("/command")
def command(request: CommandRequest, _authorized: None = Depends(verify_token)):
    try:
        with runtime_lock:
            result = get_runtime().process(request.command)
        return {"response": result.response}
    except Exception as e:
        return {"response": f"Blad Jarvisa: {e}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, reload=False)
