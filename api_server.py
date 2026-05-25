from fastapi import FastAPI
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
def chat(request: ChatRequest):
    try:
        with runtime_lock:
            result = get_runtime().process(request.message)
        return {"response": result.response}
    except Exception as e:
        return {"response": f"Blad Jarvisa: {e}"}


@app.post("/command")
def command(request: CommandRequest):
    try:
        with runtime_lock:
            result = get_runtime().process(request.command)
        return {"response": result.response}
    except Exception as e:
        return {"response": f"Blad Jarvisa: {e}"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, reload=False)
