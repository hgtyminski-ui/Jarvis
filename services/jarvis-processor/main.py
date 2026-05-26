from fastapi import FastAPI
from pydantic import BaseModel

from llm import interpret_text


app = FastAPI(title="Jarvis Processor")


class InterpretRequest(BaseModel):
    text: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/interpret")
def interpret(request: InterpretRequest):
    return {"command": interpret_text(request.text)}
