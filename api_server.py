import json
from pathlib import Path
from threading import Lock

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from actions import (
    close_app,
    create_note,
    delete_note,
    is_app_running,
    load_apps,
    load_notes,
    open_app,
)
from config import CONFIG_PATH, load_config
from notes_manager import NOTES_PATH


app = FastAPI(title="Jarvis API", docs_url=None, redoc_url=None, openapi_url=None)
runtime = None
runtime_lock = Lock()

SAFE_SETTINGS = [
    "voice_enabled",
    "whisper_model",
    "sample_rate",
    "record_seconds",
    "temperature",
    "edge_voice",
    "edge_rate",
]


class ChatRequest(BaseModel):
    message: str


class CommandRequest(BaseModel):
    command: str


class AppToggleRequest(BaseModel):
    app: str


class NoteCreateRequest(BaseModel):
    title: str = ""
    content: str


class SettingsRequest(BaseModel):
    voice_enabled: bool | None = None
    whisper_model: str | None = None
    sample_rate: int | None = None
    record_seconds: float | None = None
    temperature: float | None = None
    edge_voice: str | None = None
    edge_rate: str | None = None


INDEX_HTML = r"""
<!doctype html>
<html lang="pl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>JARVIS REMOTE</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #020408;
      --panel: rgba(6, 16, 28, 0.9);
      --panel-2: rgba(7, 24, 40, 0.94);
      --cyan: #00d9ff;
      --blue: #1b70ff;
      --violet: #8a5cff;
      --green: #00ffb3;
      --red: #ff4f7b;
      --text: #dff9ff;
      --muted: #78a7b7;
      --line: rgba(0, 217, 255, 0.34);
      --violet-line: rgba(138, 92, 255, 0.34);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 50% 12%, rgba(0, 217, 255, 0.13), transparent 28%),
        linear-gradient(rgba(0, 217, 255, 0.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(0, 217, 255, 0.03) 1px, transparent 1px),
        var(--bg);
      background-size: auto, 36px 36px, 36px 36px, auto;
      color: var(--text);
      font-family: "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
    }

    body::before {
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      background: linear-gradient(rgba(255, 255, 255, 0.035), transparent 2px);
      background-size: 100% 5px;
      opacity: 0.2;
    }

    .shell {
      width: min(1280px, 100%);
      min-height: 100vh;
      margin: 0 auto;
      padding: 20px;
    }

    .topbar {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 14px;
      align-items: end;
      padding: 8px 0 16px;
      border-bottom: 1px solid var(--line);
      box-shadow: 0 1px 0 rgba(138, 92, 255, 0.18);
    }

    h1 {
      margin: 0;
      color: var(--cyan);
      font-size: 4rem;
      line-height: 1;
      letter-spacing: 0;
      text-shadow: 0 0 18px rgba(0, 217, 255, 0.45);
    }

    .signal {
      min-width: 160px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(4, 13, 22, 0.92);
      padding: 10px 12px;
      color: var(--green);
      text-align: center;
      font-weight: 900;
      box-shadow: inset 0 0 18px rgba(0, 217, 255, 0.08), 0 0 18px rgba(0, 217, 255, 0.08);
    }

    .tabs {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin: 16px 0;
    }

    .tab-button,
    button {
      min-height: 44px;
      border: 1px solid rgba(0, 217, 255, 0.62);
      border-radius: 8px;
      background: linear-gradient(180deg, rgba(15, 55, 82, 0.9), rgba(7, 24, 40, 0.94));
      color: var(--text);
      font: inherit;
      font-weight: 900;
      cursor: pointer;
      text-shadow: 0 0 10px rgba(0, 217, 255, 0.3);
      box-shadow: inset 0 0 14px rgba(0, 217, 255, 0.08), 0 0 16px rgba(0, 217, 255, 0.08);
    }

    .tab-button:hover,
    button:hover {
      border-color: var(--cyan);
      background: linear-gradient(180deg, rgba(27, 112, 255, 0.76), rgba(10, 42, 70, 0.96));
      box-shadow: 0 0 18px rgba(0, 217, 255, 0.25), inset 0 0 16px rgba(0, 217, 255, 0.12);
    }

    .tab-button.active,
    button.primary {
      border-color: rgba(138, 92, 255, 0.9);
      background: linear-gradient(180deg, rgba(27, 112, 255, 0.94), rgba(91, 63, 190, 0.9));
      box-shadow: 0 0 22px rgba(138, 92, 255, 0.26), inset 0 0 18px rgba(0, 217, 255, 0.13);
    }

    .view { display: none; }
    .view.active { display: block; }

    .grid {
      display: grid;
      grid-template-columns: 280px minmax(320px, 1fr) 360px;
      gap: 16px;
      align-items: stretch;
    }

    .two-col {
      display: grid;
      grid-template-columns: 360px minmax(320px, 1fr);
      gap: 16px;
    }

    .panel {
      position: relative;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: linear-gradient(145deg, var(--panel), rgba(8, 9, 24, 0.88));
      padding: 14px;
      box-shadow: inset 0 0 24px rgba(0, 217, 255, 0.055), 0 0 26px rgba(0, 0, 0, 0.28);
      overflow: hidden;
    }

    .panel::before,
    .panel::after {
      content: "";
      position: absolute;
      width: 34px;
      height: 34px;
      pointer-events: none;
    }

    .panel::before {
      top: -1px;
      left: -1px;
      border-top: 2px solid var(--cyan);
      border-left: 2px solid var(--cyan);
    }

    .panel::after {
      right: -1px;
      bottom: -1px;
      border-right: 2px solid var(--violet);
      border-bottom: 2px solid var(--violet);
    }

    .panel-title {
      margin: 0 0 12px;
      color: var(--cyan);
      font-size: 0.78rem;
      font-weight: 900;
      text-transform: uppercase;
    }

    .status-list,
    .list,
    .settings-grid {
      display: grid;
      gap: 10px;
    }

    .status-row,
    .list-row {
      display: grid;
      gap: 10px;
      align-items: center;
      min-height: 42px;
      border: 1px solid rgba(0, 217, 255, 0.18);
      border-radius: 8px;
      background: rgba(2, 8, 14, 0.72);
      padding: 8px 10px;
    }

    .status-row {
      grid-template-columns: 92px 1fr;
    }

    .status-row span:first-child,
    label {
      color: var(--muted);
      font-size: 0.78rem;
      font-weight: 900;
      text-transform: uppercase;
    }

    .status-row span:last-child {
      overflow-wrap: anywhere;
    }

    label {
      display: block;
      margin: 14px 0 8px;
    }

    .hud-input,
    textarea,
    select {
      width: 100%;
      border: 1px solid rgba(0, 217, 255, 0.32);
      border-radius: 8px;
      background: rgba(2, 8, 14, 0.86);
      color: var(--text);
      font: inherit;
      outline: none;
      box-shadow: inset 0 0 16px rgba(0, 217, 255, 0.04);
    }

    .hud-input,
    select {
      height: 46px;
      padding: 0 12px;
    }

    textarea {
      min-height: 126px;
      resize: vertical;
      padding: 12px;
      line-height: 1.45;
    }

    .hud-input:focus,
    textarea:focus,
    select:focus {
      border-color: var(--cyan);
      box-shadow: 0 0 0 2px rgba(0, 217, 255, 0.14), inset 0 0 18px rgba(0, 217, 255, 0.08);
    }

    .core-panel {
      display: grid;
      grid-template-rows: auto 1fr auto;
      gap: 14px;
      min-height: 620px;
    }

    .core-wrap {
      display: grid;
      place-items: center;
      min-height: 300px;
    }

    .core {
      position: relative;
      width: min(360px, 78vw);
      aspect-ratio: 1;
      border: 1px solid rgba(0, 217, 255, 0.52);
      border-radius: 50%;
      background:
        radial-gradient(circle, rgba(0, 217, 255, 0.28) 0 10%, transparent 11% 100%),
        repeating-radial-gradient(circle, rgba(0, 217, 255, 0.15) 0 2px, transparent 2px 34px);
      box-shadow: 0 0 34px rgba(0, 217, 255, 0.22), inset 0 0 36px rgba(27, 112, 255, 0.12);
      overflow: hidden;
    }

    .core::before {
      content: "";
      position: absolute;
      inset: 13%;
      border: 1px solid rgba(138, 92, 255, 0.62);
      border-radius: 50%;
      box-shadow: inset 0 0 22px rgba(138, 92, 255, 0.12);
    }

    .core::after {
      content: "";
      position: absolute;
      inset: 50% 50% 0 50%;
      width: 48%;
      height: 2px;
      background: linear-gradient(90deg, var(--green), transparent);
      transform-origin: left center;
      animation: sweep 4s linear infinite;
      box-shadow: 0 0 14px rgba(0, 255, 179, 0.5);
    }

    .core-label {
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      color: var(--green);
      font-size: 2rem;
      font-weight: 900;
      text-shadow: 0 0 18px rgba(0, 255, 179, 0.65);
    }

    .core-tick {
      position: absolute;
      inset: 8%;
      border-radius: 50%;
      background:
        linear-gradient(90deg, transparent 49.6%, rgba(0, 217, 255, 0.34) 50%, transparent 50.4%),
        linear-gradient(0deg, transparent 49.6%, rgba(0, 217, 255, 0.34) 50%, transparent 50.4%);
    }

    @keyframes sweep { to { transform: rotate(360deg); } }

    .command-panel {
      border-top: 1px solid rgba(0, 217, 255, 0.22);
      padding-top: 14px;
    }

    .send-row,
    .quick-actions,
    .button-row {
      display: grid;
      gap: 10px;
    }

    .send-row {
      grid-template-columns: 1fr 132px;
      margin-top: 10px;
    }

    .quick-actions {
      grid-template-columns: repeat(5, minmax(0, 1fr));
      margin-top: 12px;
    }

    .button-row {
      grid-template-columns: repeat(2, minmax(0, 1fr));
      margin-top: 12px;
    }

    .danger {
      border-color: rgba(255, 79, 123, 0.78);
      background: linear-gradient(180deg, rgba(114, 22, 48, 0.9), rgba(42, 7, 22, 0.94));
    }

    .success {
      border-color: rgba(0, 255, 179, 0.7);
      background: linear-gradient(180deg, rgba(0, 112, 84, 0.84), rgba(7, 42, 35, 0.94));
    }

    .log-panel {
      min-height: 620px;
      display: grid;
      grid-template-rows: auto 1fr;
    }

    .history,
    .note-content {
      min-height: 0;
      overflow: auto;
      font-family: Consolas, "Courier New", monospace;
    }

    .history {
      max-height: 560px;
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 6px 4px 2px 0;
    }

    .entry,
    .note-content {
      border-left: 2px solid rgba(0, 217, 255, 0.58);
      background: rgba(0, 12, 20, 0.74);
      padding: 8px 10px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      line-height: 1.42;
      color: #c9f6ff;
    }

    .entry .meta {
      display: block;
      margin-bottom: 4px;
      color: var(--cyan);
      font-size: 0.76rem;
      font-weight: 900;
      text-transform: uppercase;
    }

    .entry.error { border-left-color: var(--red); color: #ffd6df; }
    .entry.error .meta { color: var(--red); }
    .entry.ok { border-left-color: var(--green); }
    .entry.ok .meta { color: var(--green); }

    .app-row {
      grid-template-columns: 1fr 108px;
    }

    .note-row {
      grid-template-columns: 1fr 92px;
    }

    .note-button {
      min-height: auto;
      border: 0;
      background: transparent;
      box-shadow: none;
      padding: 0;
      color: var(--text);
      text-align: left;
      text-shadow: none;
    }

    .note-button:hover {
      background: transparent;
      box-shadow: none;
      color: var(--cyan);
    }

    .subtle {
      display: block;
      margin-top: 3px;
      color: var(--muted);
      font-size: 0.82rem;
    }

    .settings-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    @media (max-width: 1050px) {
      .grid {
        grid-template-columns: 1fr 1fr;
      }

      .core-panel {
        grid-column: 1 / -1;
        min-height: auto;
      }

      .log-panel {
        min-height: 420px;
      }

      .two-col {
        grid-template-columns: 1fr;
      }
    }

    @media (max-width: 720px) {
      .shell {
        padding: 14px;
      }

      h1 {
        font-size: 2.35rem;
      }

      .topbar,
      .tabs,
      .grid,
      .send-row,
      .quick-actions,
      .button-row,
      .settings-grid {
        grid-template-columns: 1fr;
      }

      .signal {
        width: 100%;
        min-width: 0;
      }

      .panel {
        padding: 13px;
      }

      .core-panel,
      .log-panel {
        min-height: auto;
      }

      .core-wrap {
        min-height: 250px;
      }

      .core-label {
        font-size: 1.45rem;
      }

      button,
      .tab-button {
        min-height: 48px;
      }

      .history {
        max-height: 360px;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <h1>JARVIS REMOTE</h1>
      <div id="topSignal" class="signal">LINK: STANDBY</div>
    </header>

    <nav class="tabs" aria-label="Jarvis Remote tabs">
      <button class="tab-button active" type="button" data-tab="chat">Chat</button>
      <button class="tab-button" type="button" data-tab="apps">Aplikacje</button>
      <button class="tab-button" type="button" data-tab="notes">Notatki</button>
      <button class="tab-button" type="button" data-tab="settings">Ustawienia</button>
    </nav>

    <section id="chatView" class="view active">
      <main class="grid">
        <section class="panel">
          <h2 class="panel-title">System Status</h2>
          <div class="status-list">
            <div class="status-row"><span>Backend</span><span id="backendValue">unknown</span></div>
            <div class="status-row"><span>LM Studio</span><span id="lmValue">unknown</span></div>
            <div class="status-row"><span>Model</span><span id="modelValue">unknown</span></div>
          </div>

          <label for="token">API Token</label>
          <input id="token" class="hud-input" type="password" autocomplete="current-password" placeholder="X-Jarvis-Token">
        </section>

        <section class="panel core-panel">
          <h2 class="panel-title">Remote Core</h2>
          <div class="core-wrap">
            <div class="core" aria-label="Jarvis core online">
              <div class="core-tick"></div>
              <div class="core-label">ONLINE</div>
            </div>
          </div>

          <div class="command-panel">
            <label for="message">Command Input</label>
            <textarea id="message" placeholder="Wpisz wiadomosc albo komende..."></textarea>
            <div class="send-row">
              <button id="sendButton" class="primary" type="button">Wyslij</button>
              <button id="statusButton" type="button">Status</button>
            </div>
            <div class="quick-actions">
              <button type="button" data-command="otworz spotify">Spotify</button>
              <button type="button" data-command="otworz youtube">YouTube</button>
              <button type="button" data-command="otworz steam">Steam</button>
              <button type="button" data-command="otworz netflix">Netflix</button>
              <button id="quickStatusButton" type="button">Status</button>
            </div>
          </div>
        </section>

        <section class="panel log-panel">
          <h2 class="panel-title">Console Log</h2>
          <div id="history" class="history"></div>
        </section>
      </main>
    </section>

    <section id="appsView" class="view">
      <main class="two-col">
        <section class="panel">
          <h2 class="panel-title">Aplikacje</h2>
          <button id="refreshAppsButton" class="primary" type="button">Odswiez aplikacje</button>
          <div id="appsList" class="list" style="margin-top: 12px;"></div>
        </section>
        <section class="panel">
          <h2 class="panel-title">Apps Telemetry</h2>
          <div id="appsInfo" class="note-content">Wybierz aplikacje albo odswiez status.</div>
        </section>
      </main>
    </section>

    <section id="notesView" class="view">
      <main class="two-col">
        <section class="panel">
          <h2 class="panel-title">Notatki</h2>
          <div class="button-row">
            <button id="newNoteButton" class="primary" type="button">Nowa notatka</button>
            <button id="refreshNotesButton" type="button">Odswiez</button>
          </div>
          <div id="notesList" class="list" style="margin-top: 12px;"></div>
        </section>
        <section class="panel">
          <h2 class="panel-title">Szczegoly notatki</h2>
          <label for="noteTitle">Tytul</label>
          <input id="noteTitle" class="hud-input" type="text" placeholder="Tytul notatki">
          <label for="noteContent">Tresc</label>
          <textarea id="noteContent" placeholder="Tresc notatki..."></textarea>
          <div class="button-row">
            <button id="saveNoteButton" class="primary" type="button">Zapisz</button>
            <button id="clearNoteButton" type="button">Wyczysc</button>
          </div>
          <label>Podglad</label>
          <div id="noteDetails" class="note-content">Brak wybranej notatki.</div>
        </section>
      </main>
    </section>

    <section id="settingsView" class="view">
      <section class="panel">
        <h2 class="panel-title">Ustawienia</h2>
        <div class="settings-grid">
          <div>
            <label for="voiceEnabled">voice_enabled</label>
            <select id="voiceEnabled">
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          </div>
          <div>
            <label for="whisperModel">whisper_model</label>
            <input id="whisperModel" class="hud-input" type="text">
          </div>
          <div>
            <label for="sampleRate">sample_rate</label>
            <input id="sampleRate" class="hud-input" type="number">
          </div>
          <div>
            <label for="recordSeconds">record_seconds</label>
            <input id="recordSeconds" class="hud-input" type="number" step="0.1">
          </div>
          <div>
            <label for="temperature">temperature</label>
            <input id="temperature" class="hud-input" type="number" step="0.1">
          </div>
          <div>
            <label for="edgeVoice">edge_voice</label>
            <input id="edgeVoice" class="hud-input" type="text">
          </div>
          <div>
            <label for="edgeRate">edge_rate</label>
            <input id="edgeRate" class="hud-input" type="text">
          </div>
        </div>
        <div class="button-row">
          <button id="loadSettingsButton" type="button">Odswiez ustawienia</button>
          <button id="saveSettingsButton" class="primary" type="button">Zapisz ustawienia</button>
        </div>
      </section>
    </section>
  </div>

  <script>
    const tokenInput = document.getElementById("token");
    const messageInput = document.getElementById("message");
    const historyEl = document.getElementById("history");
    const topSignal = document.getElementById("topSignal");
    const backendValue = document.getElementById("backendValue");
    const lmValue = document.getElementById("lmValue");
    const modelValue = document.getElementById("modelValue");
    const appsList = document.getElementById("appsList");
    const appsInfo = document.getElementById("appsInfo");
    const notesList = document.getElementById("notesList");
    const noteTitle = document.getElementById("noteTitle");
    const noteContent = document.getElementById("noteContent");
    const noteDetails = document.getElementById("noteDetails");

    tokenInput.value = localStorage.getItem("jarvis_api_token") || "";
    tokenInput.addEventListener("input", () => {
      localStorage.setItem("jarvis_api_token", tokenInput.value);
    });

    function authHeaders(extra = {}) {
      return { ...extra, "X-Jarvis-Token": tokenInput.value };
    }

    function timestamp() {
      return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    function addHistory(kind, text, className = "") {
      const entry = document.createElement("div");
      entry.className = `entry ${className}`.trim();
      const meta = document.createElement("span");
      meta.className = "meta";
      meta.textContent = `[${timestamp()}] ${kind}`;
      const body = document.createElement("div");
      body.textContent = text;
      entry.append(meta, body);
      historyEl.prepend(entry);
    }

    async function readJson(response) {
      if (response.status === 401) {
        throw new Error("Unauthorized");
      }
      return response.json();
    }

    function showError(target, error) {
      const text = String(error.message || error);
      if (target) target.textContent = text;
      addHistory("ERR", text, "error");
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

    function switchTab(tabName) {
      document.querySelectorAll(".tab-button").forEach((button) => {
        button.classList.toggle("active", button.dataset.tab === tabName);
      });
      document.querySelectorAll(".view").forEach((view) => view.classList.remove("active"));
      document.getElementById(`${tabName}View`).classList.add("active");

      if (tabName === "apps") loadApps();
      if (tabName === "notes") loadNotes();
      if (tabName === "settings") loadSettings();
    }

    async function sendText() {
      const text = messageInput.value.trim();
      if (!text) return;

      const endpoint = isCommand(text) ? "/command" : "/chat";
      const bodyKey = endpoint === "/command" ? "command" : "message";
      addHistory("TX", text);
      messageInput.value = "";

      try {
        const response = await fetch(endpoint, {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ [bodyKey]: text })
        });
        const data = await readJson(response);
        addHistory("RX", data.response || "", response.ok ? "ok" : "error");
      } catch (error) {
        addHistory("AUTH", String(error.message || error), "error");
      }
    }

    async function checkStatus() {
      try {
        const response = await fetch("/status");
        const data = await response.json();
        backendValue.textContent = data.status || "unknown";
        lmValue.textContent = data.lm_studio || "unknown";
        modelValue.textContent = data.model || "unknown";
        topSignal.textContent = data.lm_studio === "online" ? "LINK: ONLINE" : "LINK: DEGRADED";
        addHistory("STATUS", `Backend: ${data.status}, LM Studio: ${data.lm_studio}, Model: ${data.model}`, response.ok ? "ok" : "error");
      } catch (error) {
        backendValue.textContent = "offline";
        lmValue.textContent = "unknown";
        modelValue.textContent = "unknown";
        topSignal.textContent = "LINK: OFFLINE";
        addHistory("STATUS", String(error), "error");
      }
    }

    async function loadApps() {
      appsList.textContent = "Ladowanie...";
      try {
        const response = await fetch("/apps", { headers: authHeaders() });
        const data = await readJson(response);
        appsList.textContent = "";
        data.apps.forEach((app) => {
          const row = document.createElement("div");
          row.className = "list-row app-row";
          const name = document.createElement("div");
          const title = document.createElement("strong");
          title.textContent = app.name;
          const state = document.createElement("span");
          state.className = "subtle";
          state.textContent = app.running ? "uruchomiona" : "zamknieta";
          name.append(title, state);
          const button = document.createElement("button");
          button.type = "button";
          button.className = app.running ? "danger" : "success";
          button.textContent = app.running ? "Zamknij" : "Otworz";
          button.addEventListener("click", () => toggleApp(app.name));
          row.append(name, button);
          appsList.append(row);
        });
        appsInfo.textContent = `Aplikacje: ${data.apps.length}`;
      } catch (error) {
        showError(appsList, error);
      }
    }

    async function toggleApp(appName) {
      appsInfo.textContent = `Wykonuje akcje: ${appName}`;
      try {
        const response = await fetch("/apps/toggle", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ app: appName })
        });
        const data = await readJson(response);
        appsInfo.textContent = data.response || "OK";
        await loadApps();
      } catch (error) {
        showError(appsInfo, error);
      }
    }

    async function loadNotes() {
      notesList.textContent = "Ladowanie...";
      try {
        const response = await fetch("/notes", { headers: authHeaders() });
        const data = await readJson(response);
        notesList.textContent = "";
        data.notes.forEach((note) => {
          const row = document.createElement("div");
          row.className = "list-row note-row";
          const openButton = document.createElement("button");
          openButton.type = "button";
          openButton.className = "note-button";
          const title = document.createElement("strong");
          title.textContent = note.title;
          const created = document.createElement("span");
          created.className = "subtle";
          created.textContent = note.created_at || "brak daty";
          openButton.append(title, created);
          openButton.addEventListener("click", () => openNote(note.id));
          const deleteButton = document.createElement("button");
          deleteButton.type = "button";
          deleteButton.className = "danger";
          deleteButton.textContent = "Usun";
          deleteButton.addEventListener("click", () => deleteNote(note.id));
          row.append(openButton, deleteButton);
          notesList.append(row);
        });
        if (!data.notes.length) notesList.textContent = "Brak notatek.";
      } catch (error) {
        showError(notesList, error);
      }
    }

    async function openNote(noteId) {
      try {
        const response = await fetch(`/notes/${encodeURIComponent(noteId)}`, { headers: authHeaders() });
        const note = await readJson(response);
        noteTitle.value = note.title || "";
        noteContent.value = note.content || "";
        noteDetails.textContent = `${note.title}\n${note.created_at || ""}\n\n${note.content || ""}`;
      } catch (error) {
        showError(noteDetails, error);
      }
    }

    async function saveNote() {
      try {
        const response = await fetch("/notes", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify({ title: noteTitle.value, content: noteContent.value })
        });
        const data = await readJson(response);
        noteDetails.textContent = data.response || "Notatka zapisana.";
        noteTitle.value = "";
        noteContent.value = "";
        await loadNotes();
      } catch (error) {
        showError(noteDetails, error);
      }
    }

    async function deleteNote(noteId) {
      try {
        const response = await fetch(`/notes/${encodeURIComponent(noteId)}`, {
          method: "DELETE",
          headers: authHeaders()
        });
        const data = await readJson(response);
        noteDetails.textContent = data.response || "Notatka usunieta.";
        await loadNotes();
      } catch (error) {
        showError(noteDetails, error);
      }
    }

    function clearNoteEditor() {
      noteTitle.value = "";
      noteContent.value = "";
      noteDetails.textContent = "Nowa notatka.";
    }

    async function loadSettings() {
      try {
        const response = await fetch("/settings", { headers: authHeaders() });
        const data = await readJson(response);
        document.getElementById("voiceEnabled").value = String(Boolean(data.voice_enabled));
        document.getElementById("whisperModel").value = data.whisper_model ?? "";
        document.getElementById("sampleRate").value = data.sample_rate ?? "";
        document.getElementById("recordSeconds").value = data.record_seconds ?? "";
        document.getElementById("temperature").value = data.temperature ?? "";
        document.getElementById("edgeVoice").value = data.edge_voice ?? "";
        document.getElementById("edgeRate").value = data.edge_rate ?? "";
        addHistory("SETTINGS", "Ustawienia zaladowane.", "ok");
      } catch (error) {
        addHistory("AUTH", String(error.message || error), "error");
      }
    }

    async function saveSettings() {
      const payload = {
        voice_enabled: document.getElementById("voiceEnabled").value === "true"
      };
      const textFields = [
        ["whisper_model", "whisperModel"],
        ["edge_voice", "edgeVoice"],
        ["edge_rate", "edgeRate"]
      ];
      const numberFields = [
        ["sample_rate", "sampleRate"],
        ["record_seconds", "recordSeconds"],
        ["temperature", "temperature"]
      ];
      textFields.forEach(([key, id]) => {
        const value = document.getElementById(id).value;
        if (value !== "") payload[key] = value;
      });
      numberFields.forEach(([key, id]) => {
        const value = document.getElementById(id).value;
        if (value !== "") payload[key] = Number(value);
      });
      try {
        const response = await fetch("/settings", {
          method: "POST",
          headers: authHeaders({ "Content-Type": "application/json" }),
          body: JSON.stringify(payload)
        });
        await readJson(response);
        addHistory("SETTINGS", "Ustawienia zapisane.", "ok");
      } catch (error) {
        addHistory("AUTH", String(error.message || error), "error");
      }
    }

    document.querySelectorAll(".tab-button").forEach((button) => {
      button.addEventListener("click", () => switchTab(button.dataset.tab));
    });
    document.getElementById("sendButton").addEventListener("click", sendText);
    document.getElementById("statusButton").addEventListener("click", checkStatus);
    document.getElementById("quickStatusButton").addEventListener("click", checkStatus);
    document.getElementById("refreshAppsButton").addEventListener("click", loadApps);
    document.getElementById("refreshNotesButton").addEventListener("click", loadNotes);
    document.getElementById("newNoteButton").addEventListener("click", clearNoteEditor);
    document.getElementById("clearNoteButton").addEventListener("click", clearNoteEditor);
    document.getElementById("saveNoteButton").addEventListener("click", saveNote);
    document.getElementById("loadSettingsButton").addEventListener("click", loadSettings);
    document.getElementById("saveSettingsButton").addEventListener("click", saveSettings);
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
        expected_token = load_config().get("api_token")
    except Exception:
        expected_token = None

    if not expected_token or x_jarvis_token != expected_token:
        raise HTTPException(status_code=401, detail="Unauthorized")


def note_path_from_id(note_id: str) -> Path:
    try:
        resolved_notes_path = NOTES_PATH.resolve()
        resolved_note_path = (NOTES_PATH / note_id).resolve()
    except (OSError, TypeError, ValueError):
        raise HTTPException(status_code=404, detail="Note not found")

    if resolved_note_path.parent != resolved_notes_path:
        raise HTTPException(status_code=404, detail="Note not found")

    if resolved_note_path.suffix.lower() not in [".json", ".txt"]:
        raise HTTPException(status_code=404, detail="Note not found")

    if not resolved_note_path.exists():
        raise HTTPException(status_code=404, detail="Note not found")

    return resolved_note_path


def note_to_public(note: dict):
    note_path = Path(str(note.get("path") or ""))
    return {
        "id": note_path.name,
        "filename": note_path.name,
        "title": str(note.get("title") or "Bez tytulu"),
        "created_at": str(note.get("created_at") or ""),
    }


def safe_settings(config: dict):
    return {name: config.get(name) for name in SAFE_SETTINGS}


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


@app.get("/apps")
def get_apps(_authorized: None = Depends(verify_token)):
    apps = [
        {"name": name, "running": is_app_running(name)}
        for name in sorted(load_apps().keys())
    ]
    return {"apps": apps}


@app.post("/apps/toggle")
def toggle_app(request: AppToggleRequest, _authorized: None = Depends(verify_token)):
    app_name = request.app.strip().lower()
    if not app_name:
        return {"response": "Brak nazwy aplikacji."}

    try:
        if is_app_running(app_name):
            result = close_app(app_name)
            return {"response": f"Zamykam {app_name}.", "result": result}

        result = open_app(app_name)
        if result == "opened":
            return {"response": f"Otwieram {app_name}.", "result": result}
        return {"response": f"Nie znam aplikacji: {app_name}.", "result": result}
    except Exception as e:
        return {"response": f"Blad aplikacji: {e}"}


@app.get("/notes")
def get_notes(_authorized: None = Depends(verify_token)):
    return {"notes": [note_to_public(note) for note in load_notes()]}


@app.get("/notes/{note_id}")
def get_note(note_id: str, _authorized: None = Depends(verify_token)):
    note_path = note_path_from_id(note_id)
    for note in load_notes():
        if Path(str(note.get("path") or "")).name == note_path.name:
            public_note = note_to_public(note)
            public_note["content"] = str(note.get("content") or "")
            return public_note

    raise HTTPException(status_code=404, detail="Note not found")


@app.post("/notes")
def post_note(request: NoteCreateRequest, _authorized: None = Depends(verify_token)):
    result = create_note(request.content, request.title)
    if result == "saved":
        return {"response": "Notatka zapisana."}
    return {"response": "Brakuje tresci notatki."}


@app.delete("/notes/{note_id}")
def remove_note(note_id: str, _authorized: None = Depends(verify_token)):
    note_path = note_path_from_id(note_id)
    result = delete_note(str(note_path))
    if result == "deleted":
        return {"response": "Notatka usunieta."}
    if result == "missing":
        raise HTTPException(status_code=404, detail="Note not found")
    return {"response": "Nie udalo sie usunac notatki.", "result": result}


@app.get("/settings")
def get_settings(_authorized: None = Depends(verify_token)):
    return safe_settings(load_config())


@app.post("/settings")
def post_settings(request: SettingsRequest, _authorized: None = Depends(verify_token)):
    config = load_config()
    if hasattr(request, "model_dump"):
        updates = request.model_dump(exclude_unset=True)
    else:
        updates = request.dict(exclude_unset=True)

    for key, value in updates.items():
        if key not in SAFE_SETTINGS:
            continue
        if value is None:
            continue
        config[key] = value

    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return safe_settings(config)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host="127.0.0.1", port=8000, reload=False)
