import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

import customtkinter as ctk


ROOT_DIR = Path(__file__).resolve().parent
PROCESSOR_DIR = ROOT_DIR / "services" / "jarvis-processor"
CONFIG_PATH = ROOT_DIR / "config.json"

BG = "#05070d"
PANEL = "#0b1220"
PANEL_2 = "#0f1b2d"
CYAN = "#00eaff"
BLUE = "#2f7dff"
PURPLE = "#8a5cff"
TEXT = "#d7f7ff"
MUTED = "#78a7b7"
SUCCESS = "#20e080"
DANGER = "#ff3b5c"
UNKNOWN = "#8a5cff"

LM_STUDIO_URL = "http://127.0.0.1:1233/v1/models"
PROCESSOR_HEALTH_URL = "http://127.0.0.1:8001/health"
PROCESSOR_STATUS_URL = "http://127.0.0.1:8001/status"
BACKEND_STATUS_URL = "http://127.0.0.1:8000/status"
BACKEND_AGENTS_URL = "http://127.0.0.1:8000/agents"
PAIRING_QR_URL = "http://127.0.0.1:8000/pairing-qr"


def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def request_json(url, headers=None, timeout=1.5):
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body) if body else {}


class JarvisControlCenter(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        super().__init__()

        self.title("Jarvis Control Center")
        self.geometry("980x640")
        self.minsize(860, 560)
        self.configure(fg_color=BG)

        self.processes = {}
        self.status_labels = {}
        self.status_dots = {}

        self.build_ui()
        self.refresh_status()

    def build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=26, pady=(22, 12))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="JARVIS CONTROL CENTER",
            text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=22, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        subtitle = ctk.CTkLabel(
            header,
            text="LOCAL HUB / PROCESSOR / AGENT",
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        subtitle.grid(row=1, column=0, sticky="w", pady=(4, 0))

        self.refresh_button = self.make_button(
            header,
            "Odśwież status",
            self.refresh_status,
            border_color=CYAN,
            hover_color=BLUE,
        )
        self.refresh_button.grid(row=0, column=1, rowspan=2, sticky="e")

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=0, sticky="nsew", padx=26, pady=(0, 20))
        main.grid_columnconfigure(0, weight=1)
        main.grid_columnconfigure(1, weight=1)
        main.grid_rowconfigure(1, weight=1)

        status_panel = self.make_panel(main, "SYSTEM STATUS")
        status_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=(0, 16))

        for row, name in enumerate(["LM Studio", "Processor", "Backend", "Agent"]):
            self.add_status_row(status_panel, row, name)

        actions_panel = self.make_panel(main, "START SERVICES")
        actions_panel.grid(row=0, column=1, sticky="nsew", padx=(10, 0), pady=(0, 16))
        actions_panel.grid_columnconfigure((0, 1), weight=1)

        self.make_button(actions_panel, "Start Processor", self.start_processor, border_color=PURPLE).grid(
            row=0, column=0, sticky="ew", padx=(0, 8), pady=(0, 10)
        )
        self.make_button(actions_panel, "Start Backend", self.start_backend, border_color=CYAN).grid(
            row=0, column=1, sticky="ew", padx=(8, 0), pady=(0, 10)
        )
        self.make_button(actions_panel, "Start Agent", self.start_agent, border_color=BLUE).grid(
            row=1, column=0, sticky="ew", padx=(0, 8)
        )
        self.make_button(actions_panel, "Połącz telefon", self.open_pairing, border_color=PURPLE).grid(
            row=1, column=1, sticky="ew", padx=(8, 0)
        )

        log_panel = self.make_panel(main, "EVENT LOG")
        log_panel.grid(row=1, column=0, columnspan=2, sticky="nsew")
        log_panel.grid_rowconfigure(0, weight=1)
        log_panel.grid_columnconfigure(0, weight=1)

        self.log_box = ctk.CTkTextbox(
            log_panel,
            fg_color=PANEL_2,
            text_color=TEXT,
            border_color="#123249",
            border_width=1,
            corner_radius=8,
            font=ctk.CTkFont(family="Consolas", size=11),
            height=220,
        )
        self.log_box.grid(row=0, column=0, sticky="nsew")
        self.log_box.configure(state="disabled")

    def make_panel(self, parent, title):
        frame = ctk.CTkFrame(parent, fg_color=PANEL, border_color="#123249", border_width=1, corner_radius=8)
        frame.grid_columnconfigure(0, weight=1)

        label = ctk.CTkLabel(
            frame,
            text=title,
            text_color=CYAN,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
        )
        label.grid(row=0, column=0, columnspan=3, sticky="w", padx=16, pady=(14, 12))
        return frame

    def make_button(self, parent, text, command, border_color=CYAN, hover_color=None):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color=PANEL_2,
            hover_color=hover_color or "#13233a",
            text_color=TEXT,
            border_color=border_color,
            border_width=1,
            corner_radius=8,
            height=42,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
        )

    def add_status_row(self, parent, row, name):
        actual_row = row + 1
        label = ctk.CTkLabel(
            parent,
            text=name,
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
        )
        label.grid(row=actual_row, column=0, sticky="w", padx=16, pady=8)

        dot = ctk.CTkLabel(parent, text="●", text_color=UNKNOWN, font=ctk.CTkFont(size=13, weight="bold"))
        dot.grid(row=actual_row, column=1, sticky="e", padx=(8, 4), pady=8)

        value = ctk.CTkLabel(parent, text="Nieznany", text_color=TEXT, font=ctk.CTkFont(family="Consolas", size=12))
        value.grid(row=actual_row, column=2, sticky="e", padx=(4, 16), pady=8)

        self.status_dots[name] = dot
        self.status_labels[name] = value

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("1.0", f"[{timestamp}] {message}\n")
        lines = self.log_box.get("1.0", "end-1c").splitlines()
        if len(lines) > 80:
            self.log_box.delete("81.0", "end")
        self.log_box.configure(state="disabled")

    def set_status(self, name, state, detail=None):
        color = SUCCESS if state == "Online" else DANGER if state == "Offline" else UNKNOWN
        self.status_dots[name].configure(text_color=color)
        self.status_labels[name].configure(text=detail or state, text_color=TEXT)

    def refresh_status(self):
        self.refresh_button.configure(state="disabled", text="Sprawdzam...")
        threading.Thread(target=self._refresh_status_worker, daemon=True).start()

    def _refresh_status_worker(self):
        statuses = {
            "LM Studio": self.check_lm_studio(),
            "Processor": self.check_processor(),
            "Backend": self.check_backend(),
            "Agent": self.check_agent(),
        }
        self.after(0, lambda: self.apply_statuses(statuses))

    def apply_statuses(self, statuses):
        for name, (state, detail) in statuses.items():
            self.set_status(name, state, detail)
            self.log(f"{name}: {detail or state}")
        self.refresh_button.configure(state="normal", text="Odśwież status")

    def check_lm_studio(self):
        try:
            status, _ = request_json(LM_STUDIO_URL)
            return ("Online", "Online") if status == 200 else ("Offline", "Offline")
        except Exception:
            return "Offline", "Offline"

    def check_processor(self):
        for url in [PROCESSOR_HEALTH_URL, PROCESSOR_STATUS_URL]:
            try:
                status, _ = request_json(url)
                if status == 200:
                    return "Online", "Online"
            except Exception:
                continue
        return "Offline", "Offline"

    def check_backend(self):
        try:
            status, data = request_json(BACKEND_STATUS_URL)
            if status == 200:
                return "Online", str(data.get("status") or "Online")
        except Exception:
            pass
        return "Offline", "Offline"

    def check_agent(self):
        token = load_config().get("api_token") or ""
        headers = {"X-Jarvis-Token": token} if token else {}
        try:
            status, data = request_json(BACKEND_AGENTS_URL, headers=headers)
            agents = data.get("agents") if isinstance(data, dict) else []
            if status == 200 and agents:
                return "Online", ", ".join(str(agent) for agent in agents)
            if status == 200:
                return "Offline", "Brak agentów"
        except urllib.error.HTTPError as error:
            if error.code == 401:
                return "Unknown", "Token wymagany"
        except Exception:
            pass
        return "Offline", "Offline"

    def is_tracked_process_running(self, key):
        process = self.processes.get(key)
        return process is not None and process.poll() is None

    def start_process_once(self, key, args, cwd, online_check, started_message):
        if self.is_tracked_process_running(key):
            self.log(f"{started_message}: już działa")
            return

        state, _ = online_check()
        if state == "Online":
            self.log(f"{started_message}: już online")
            return

        try:
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform.startswith("win") else 0
            process = subprocess.Popen(
                args,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            self.processes[key] = process
            self.log(started_message)
            self.after(1200, self.refresh_status)
        except Exception as error:
            self.log(f"Błąd startu {key}: {error}")

    def start_processor(self):
        self.start_process_once(
            "processor",
            [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8001"],
            PROCESSOR_DIR,
            self.check_processor,
            "Uruchomiono processor",
        )

    def start_backend(self):
        self.start_process_once(
            "backend",
            [sys.executable, "-m", "uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"],
            ROOT_DIR,
            self.check_backend,
            "Uruchomiono backend",
        )

    def start_agent(self):
        self.start_process_once(
            "agent",
            [sys.executable, "jarvis_agent.py"],
            ROOT_DIR,
            self.check_agent,
            "Uruchomiono agent",
        )

    def open_pairing(self):
        webbrowser.open(PAIRING_QR_URL)
        self.log("Otwieram pairing telefonu")


if __name__ == "__main__":
    app = JarvisControlCenter()
    app.mainloop()
