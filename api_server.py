from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from threading import Lock


app = FastAPI(title="Jarvis API")
runtime = None
runtime_lock = Lock()


class ChatRequest(BaseModel):
    message: str


class CommandRequest(BaseModel):
    command: str


INDEX_HTML = r"""
<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Jarvis Remote</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #05070b;
      --panel: #0b111a;
      --panel-2: #07131d;
      --cyan: #00d9ff;
      --blue: #1b70ff;
      --green: #00c777;
      --red: #ff4f70;
      --text: #d9f7ff;
      --muted: #7198a8;
      --line: #12384a;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .shell {
      width: min(920px, 100%);
      margin: 0 auto;
      padding: 22px;
    }

    header {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 14px;
      padding: 6px 0 16px;
      border-bottom: 1px solid var(--cyan);
    }

    h1 {
      margin: 0;
      color: var(--cyan);
      font-size: clamp(2rem, 7vw, 3.6rem);
      line-height: 1;
      letter-spacing: 0;
    }

    .status-pill {
      min-width: 132px;
      padding: 9px 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      color: var(--muted);
      text-align: center;
      font-size: 0.92rem;
      font-weight: 700;
    }

    main {
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
      padding-top: 16px;
    }

    .panel {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      padding: 14px;
    }

    label {
      display: block;
      margin-bottom: 7px;
      color: var(--muted);
      font-size: 0.86rem;
      font-weight: 700;
    }

    input,
    textarea {
      width: 100%;
      border: 1px solid #16445a;
      border-radius: 8px;
      background: #050b12;
      color: var(--text);
      font: inherit;
      outline: none;
    }

    input {
      height: 44px;
      padding: 0 12px;
    }

    textarea {
      min-height: 104px;
      resize: vertical;
      padding: 12px;
      line-height: 1.45;
    }

    input:focus,
    textarea:focus {
      border-color: var(--cyan);
      box-shadow: 0 0 0 2px rgba(0, 217, 255, 0.14);
    }

    .actions,
    .quick-actions {
      display: grid;
      gap: 10px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 12px;
    }

    .quick-actions {
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }

    button {
      min-height: 42px;
      border: 1px solid #176684;
      border-radius: 8px;
      background: #0d2f45;
      color: var(--text);
      font: inherit;
      font-weight: 800;
      cursor: pointer;
    }

    button:hover {
      background: #124f70;
    }

    button.primary {
      border-color: var(--blue);
      background: var(--blue);
    }

    button.primary:hover {
      background: #2f83ff;
    }

    .history {
      min-height: 220px;
      max-height: 48vh;
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding-right: 2px;
    }

    .entry {
      border: 1px solid #11364a;
      border-radius: 8px;
      background: var(--panel-2);
      padding: 10px 12px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      line-height: 1.42;
    }

    .entry .meta {
      display: block;
      margin-bottom: 5px;
      color: var(--muted);
      font-size: 0.78rem;
      font-weight: 800;
      text-transform: uppercase;
    }

    .entry.error {
      border-color: #7a1d32;
      color: #ffd8df;
    }

    .entry.ok {
      border-color: #176b52;
    }

    @media (max-width: 640px) {
      .shell {
        padding: 14px;
      }

      header {
        align-items: stretch;
        flex-direction: column;
      }

      .status-pill {
        width: 100%;
      }

      .actions,
      .quick-actions {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <h1>Jarvis Remote</h1>
      <div id="backendStatus" class="status-pill">Status: unknown</div>
    </header>

    <main>
      <section class="panel">
        <label for="token">Token API</label>
        <input id="token" type="password" autocomplete="current-password" placeholder="X-Jarvis-Token">
      </section>

      <section class="panel">
        <label for="message">Wiadomosc lub komenda</label>
        <textarea id="message" placeholder="Napisz do Jarvisa..."></textarea>
        <div class="actions">
          <button id="sendButton" class="primary" type="button">Wyslij</button>
          <button id="statusButton" type="button">Status</button>
        </div>
        <div class="quick-actions">
          <button type="button" data-command="otworz spotify">Spotify</button>
          <button type="button" data-command="otworz youtube">YouTube</button>
          <button type="button" data-command="otworz steam">Steam</button>
          <button type="button" data-command="otworz netflix">Netflix</button>
        </div>
      </section>

      <section class="panel">
        <label>Historia odpowiedzi</label>
        <div id="history" class="history"></div>
      </section>
    </main>
  </div>

  <script>
    const tokenInput = document.getElementById("token");
    const messageInput = document.getElementById("message");
    const historyEl = document.getElementById("history");
    const statusEl = document.getElementById("backendStatus");

    tokenInput.value = localStorage.getItem("jarvis_api_token") || "";
    tokenInput.addEventListener("input", () => {
      localStorage.setItem("jarvis_api_token", tokenInput.value);
    });

    function addHistory(kind, text, className = "") {
      const entry = document.createElement("div");
      entry.className = `entry ${className}`.trim();
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = kind;
      const body = document.createElement("div");
      body.textContent = text;
      entry.append(meta, body);
      historyEl.prepend(entry);
    }

    function isCommand(text) {
      const normalized = text.trim().toLowerCase();
      return (
        normalized.startsWith("otworz") ||
        normalized.startsWith("otwórz") ||
        normalized.startsWith("zamknij") ||
        normalized.startsWith("pusc") ||
        normalized.startsWith("puść") ||
        normalized.startsWith("znajdz na spotify") ||
        normalized.startsWith("znajdź na spotify")
      );
    }

    async function sendText() {
      const text = messageInput.value.trim();
      if (!text) {
        return;
      }

      const endpoint = isCommand(text) ? "/command" : "/chat";
      const bodyKey = endpoint === "/command" ? "command" : "message";
      addHistory("Ty", text);
      messageInput.value = "";

      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Jarvis-Token": tokenInput.value
          },
          body: JSON.stringify({ [bodyKey]: text })
        });

        if (response.status === 401) {
          addHistory("Jarvis", "Unauthorized", "error");
          return;
        }

        const data = await response.json();
        addHistory("Jarvis", data.response || "", response.ok ? "ok" : "error");
      } catch (error) {
        addHistory("Jarvis", String(error), "error");
      }
    }

    async function checkStatus() {
      try {
        const response = await fetch("/status");
        const data = await response.json();
        const text = `Backend: ${data.status}, LM Studio: ${data.lm_studio}, model: ${data.model}`;
        statusEl.textContent = data.lm_studio === "online" ? "Status: online" : "Status: offline";
        addHistory("Status", text, response.ok ? "ok" : "error");
      } catch (error) {
        statusEl.textContent = "Status: offline";
        addHistory("Status", String(error), "error");
      }
    }

    document.getElementById("sendButton").addEventListener("click", sendText);
    document.getElementById("statusButton").addEventListener("click", checkStatus);
    document.querySelectorAll("[data-command]").forEach((button) => {
      button.addEventListener("click", () => {
        messageInput.value = button.dataset.command;
        sendText();
      });
    });

    messageInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendText();
      }
    });

    checkStatus();
  </script>
</body>
</html>
"""


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


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML


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
