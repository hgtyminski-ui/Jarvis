import json
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime
from pathlib import Path

import customtkinter as ctk

from actions import app_label_from_entry, close_app, create_note, delete_note, load_apps_raw, load_notes, open_app
from app_scanner import (
    clean_apps_json,
    load_existing_apps,
    merge_discovered_apps,
    normalize_app_key,
    save_apps_json,
    scan_installed_apps,
)


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
LINE = "#123249"

LM_STUDIO_URL = "http://127.0.0.1:1233/v1/models"
PROCESSOR_HEALTH_URL = "http://127.0.0.1:8001/health"
PROCESSOR_STATUS_URL = "http://127.0.0.1:8001/status"
BACKEND_STATUS_URL = "http://127.0.0.1:8000/status"
BACKEND_AGENTS_URL = "http://127.0.0.1:8000/agents"
PHONE_STATUS_URL = "http://127.0.0.1:8000/phone/status"
PAIRING_QR_URL = "http://127.0.0.1:8000/pairing-qr"


def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def request_json(url, headers=None, timeout=1.5):
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body) if body else {}


def post_json(url, payload, headers=None, timeout=12):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request_headers = {"Content-Type": "application/json"}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, data=body, headers=request_headers, method="POST")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        text = response.read().decode("utf-8")
        return response.status, json.loads(text) if text else {}


def entry_launch_path(entry):
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return str(entry.get("launch_path") or entry.get("path") or entry.get("uri") or "")
    return ""


def entry_type(entry):
    if isinstance(entry, dict):
        return str(entry.get("type") or "app")
    path = entry_launch_path(entry)
    suffix = Path(path).suffix.lower()
    if suffix == ".lnk":
        return "lnk"
    if suffix == ".exe":
        return "exe"
    if ":" in path:
        return "uri"
    return "app"


def is_discovered(entry):
    return isinstance(entry, dict) and bool(entry.get("discovered"))


def is_hidden(entry):
    return isinstance(entry, dict) and bool(entry.get("hidden"))


def short_path(path, limit=60):
    text = str(path or "")
    if len(text) <= limit:
        return text or "brak ścieżki"
    return f"...{text[-limit:]}"


class JarvisControlCenter(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        super().__init__()

        self.title("Jarvis Control Center")
        self.geometry("1440x820")
        self.minsize(1120, 680)
        self.configure(fg_color=BG)

        self.processes = {}
        self.status_labels = {}
        self.status_dots = {}
        self.tabs = {}
        self.views = {}
        self.active_tab = "chat"
        self.app_filter = tk.StringVar(value="Wszystkie")
        self.app_search = tk.StringVar(value="")
        self.manual_label = tk.StringVar(value="")
        self.manual_key = tk.StringVar(value="")
        self.manual_type = tk.StringVar(value="exe")
        self.manual_command = tk.StringVar(value="")
        self.manual_arguments = tk.StringVar(value="")
        self.manual_selected_text = tk.StringVar(value="Nie wybrano pliku")
        self.apps_cache = []
        self.apps_loaded = False
        self.apps_loading = False
        self.apps_page = 0
        self.apps_per_page = 50
        self.scan_app_buttons = []
        config = load_config()
        self.backend_url = tk.StringVar(value=str(config.get("backend_url") or "http://127.0.0.1:8000"))
        self.api_token = tk.StringVar(value=str(config.get("api_token") or ""))
        self.device_id = tk.StringVar(value=str(config.get("device_id") or "local-pc"))
        self.text_scale = tk.StringVar(value=str(config.get("text_scale") or "1.0"))
        self.hud_scale = tk.StringVar(value=str(config.get("hud_scale") or "1.15"))
        self.last_valid_text_scale = self.parse_scale_value(self.text_scale.get(), 1.0, 0.6, 1.8)
        self.last_valid_hud_scale = self.parse_scale_value(self.hud_scale.get(), 1.15, 0.6, 1.5)
        self.text_scale.set(f"{self.last_valid_text_scale:.2f}")
        self.hud_scale.set(f"{self.last_valid_hud_scale:.2f}")
        self.show_status_panel = tk.BooleanVar(value=bool(config.get("show_system_status", True)))
        self.show_console_log = tk.BooleanVar(value=bool(config.get("show_console_log", True)))
        self.voice_enabled = tk.BooleanVar(value=bool(config.get("voice_enabled", True)))
        self.voice_language = tk.StringVar(value=str(config.get("voice_language") or "pl-PL"))
        self.voice_rate = tk.StringVar(value=str(config.get("voice_rate") or config.get("edge_rate") or "+0%"))
        self.voice_pitch = tk.StringVar(value=str(config.get("voice_pitch") or "+0Hz"))
        self.microphone_enabled = tk.BooleanVar(value=bool(config.get("microphone_enabled", True)))
        self.ptt_mode = tk.BooleanVar(value=bool(config.get("ptt_mode", True)))
        self.chat_input = tk.StringVar(value="")
        self.note_title_var = tk.StringVar(value="")
        self.note_selected = None

        self.build_ui()
        self.switch_tab("chat")
        self.refresh_status()

    def build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.bg_canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg_canvas.bind("<Configure>", self.draw_grid)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=self.scale_hud(28), pady=self.hud_pad((20, 12)))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="JARVIS CONTROL CENTER",
            text_color=TEXT,
            font=self.ui_font(18, "bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        tabs = ctk.CTkFrame(header, fg_color="transparent")
        tabs.grid(row=1, column=0, sticky="w", pady=self.hud_pad((12, 0)))
        for index, tab in enumerate(["CHAT", "APLIKACJE", "NOTATKI", "USTAWIENIA", "CONTROL"]):
            key = tab.lower()
            button = self.make_button(tabs, tab, lambda name=key: self.switch_tab(name), width=120, height=30)
            button.grid(row=0, column=index, padx=self.hud_pad((0, 8)), sticky="w")
            self.tabs[key] = button

        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.grid(row=1, column=0, sticky="nsew", padx=self.scale_hud(28), pady=self.hud_pad((0, 24)))
        shell.grid_columnconfigure(0, minsize=self.scale_hud(260), weight=0)
        shell.grid_columnconfigure(1, weight=1)
        shell.grid_columnconfigure(2, minsize=self.scale_hud(300), weight=0)
        shell.grid_rowconfigure(0, weight=1)

        self.status_panel = self.make_panel(shell, "SYSTEM STATUS")
        self.status_panel.grid(row=0, column=0, sticky="nsew", padx=self.hud_pad((0, 14)))
        self.build_status_panel()

        self.content = ctk.CTkFrame(shell, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.build_views()

        self.log_panel = self.make_panel(shell, "CONSOLE LOG")
        self.log_panel.grid(row=0, column=2, sticky="nsew", padx=self.hud_pad((14, 0)))
        self.log_panel.grid_rowconfigure(1, weight=1)
        self.log_panel.grid_columnconfigure(0, weight=1)
        self.build_log_panel()
        self.apply_panel_visibility()

    def scale_text(self, value):
        scale = getattr(self, "last_valid_text_scale", 1.0)
        return max(1, int(round(value * scale)))

    def scale_hud(self, value):
        scale = getattr(self, "last_valid_hud_scale", 1.15)
        return max(1, int(round(value * scale)))

    def ui_font(self, size, weight=None, family="Consolas"):
        return ctk.CTkFont(family=family, size=self.scale_text(size), weight=weight)

    def hud_pad(self, value):
        if isinstance(value, tuple):
            return tuple(self.scale_hud(item) for item in value)
        return self.scale_hud(value)

    def rebuild_scaled_ui(self, current_tab):
        current_tab = current_tab if current_tab in {"chat", "aplikacje", "notatki", "ustawienia", "control"} else "chat"
        for child in self.winfo_children():
            child.destroy()
        self.status_labels = {}
        self.status_dots = {}
        self.tabs = {}
        self.views = {}
        self.scan_app_buttons = []
        self.build_ui()
        self.switch_tab(current_tab)
        self.refresh_status()

    def draw_grid(self, event=None):
        self.bg_canvas.delete("grid")
        width = self.bg_canvas.winfo_width()
        height = self.bg_canvas.winfo_height()
        for x in range(0, width, 44):
            self.bg_canvas.create_line(x, 0, x, height, fill="#071425", tags="grid")
        for y in range(0, height, 44):
            self.bg_canvas.create_line(0, y, width, y, fill="#071425", tags="grid")
        for x in range(0, width, 22):
            for y in range(0, height, 22):
                self.bg_canvas.create_oval(x, y, x + 1, y + 1, fill="#0b2736", outline="", tags="grid")

    def make_panel(self, parent, title):
        frame = ctk.CTkFrame(parent, fg_color=PANEL, border_color=LINE, border_width=1, corner_radius=self.scale_hud(8))
        frame.grid_columnconfigure(0, weight=1)
        label = ctk.CTkLabel(
            frame,
            text=title,
            text_color=CYAN,
            font=self.ui_font(11, "bold"),
        )
        label.grid(row=0, column=0, sticky="w", padx=self.scale_hud(14), pady=self.hud_pad((12, 8)))
        return frame

    def make_button(self, parent, text, command, border_color=CYAN, hover_color=None, width=170, height=38):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color=PANEL_2,
            hover_color=hover_color or "#13233a",
            text_color=TEXT,
            border_color=border_color,
            border_width=1,
            corner_radius=self.scale_hud(8),
            width=self.scale_hud(width),
            height=self.scale_hud(height),
            font=self.ui_font(11, "bold"),
        )

    def bind_ctrl_backspace(self, widget):
        def handler(event):
            self.delete_previous_word(event.widget)
            return "break"

        sequences = (
            "<Control-KeyPress-BackSpace>",
            "<Control-BackSpace>",
        )

        for sequence in sequences:
            try:
                widget.bind(sequence, handler, add="+")
            except Exception:
                pass

        return widget

    def delete_previous_word(self, widget):
        try:
            cursor = widget.index("insert")
            try:
                before = widget.get("1.0", cursor)
                delete_chars = self.previous_word_delete_count(before)
                if delete_chars > 0:
                    widget.delete(f"insert-{delete_chars}c", "insert")
                return "break"
            except Exception:
                before = widget.get()[:cursor]
                delete_chars = self.previous_word_delete_count(before)
                if delete_chars > 0:
                    widget.delete(cursor - delete_chars, cursor)
                return "break"
        except Exception:
            return "break"

    def previous_word_delete_count(self, text):
        if not text:
            return 0
        index = len(text)
        while index > 0 and text[index - 1].isspace():
            index -= 1
        while index > 0 and not text[index - 1].isspace():
            index -= 1
        return len(text) - index

    def build_status_panel(self):
        config = load_config()
        rows = [
            ("LM Studio", "Nieznany"),
            ("Processor", "Nieznany"),
            ("Backend", "Nieznany"),
            ("Agent", "Nieznany"),
            ("Telefon", "Nieznany"),
            ("Model", str(config.get("model") or "local-model")),
            ("Device ID", str(config.get("device_id") or "local-pc")),
        ]
        for row, (name, value) in enumerate(rows, start=1):
            self.add_status_row(self.status_panel, row, name, value)

    def add_status_row(self, parent, row, name, value):
        row_frame = ctk.CTkFrame(parent, fg_color="transparent")
        row_frame.grid(row=row, column=0, sticky="ew", padx=self.scale_hud(14), pady=self.scale_hud(5))
        row_frame.grid_columnconfigure(1, weight=1)

        dot = ctk.CTkLabel(row_frame, text="●", text_color=UNKNOWN, font=self.ui_font(9, "bold"))
        dot.grid(row=0, column=0, padx=self.hud_pad((0, 8)), sticky="w")
        label = ctk.CTkLabel(
            row_frame,
            text=name.upper(),
            text_color=MUTED,
            anchor="w",
            font=self.ui_font(9, "bold"),
        )
        label.grid(row=0, column=1, sticky="w")
        value_label = ctk.CTkLabel(
            row_frame,
            text=value,
            text_color=TEXT,
            anchor="e",
            font=self.ui_font(9),
        )
        value_label.grid(row=0, column=2, padx=self.hud_pad((8, 0)), sticky="e")

        self.status_dots[name] = dot
        self.status_labels[name] = value_label

    def build_log_panel(self):
        self.log_box = ctk.CTkTextbox(
            self.log_panel,
            fg_color="#07101d",
            text_color=TEXT,
            border_color="#123249",
            border_width=1,
            corner_radius=self.scale_hud(8),
            font=self.ui_font(10),
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=self.scale_hud(12), pady=self.hud_pad((0, 12)))
        self.log_box.configure(state="disabled")

    def build_views(self):
        self.views["control"] = self.create_control_view()
        self.views["aplikacje"] = self.create_apps_view()
        self.views["ustawienia"] = self.create_settings_view()
        self.views["chat"] = self.create_chat_view()
        self.views["notatki"] = self.create_notes_view()

    def switch_tab(self, tab):
        if tab not in self.views:
            tab = "chat"
        self.active_tab = tab
        for key, view in self.views.items():
            view.grid_remove()
        self.views[tab].grid(row=0, column=0, sticky="nsew")

        for key, button in self.tabs.items():
            active = key == tab
            button.configure(border_color=PURPLE if active else CYAN, text_color=TEXT if active else MUTED)

        if tab == "aplikacje":
            self.load_apps_view_once()
        elif tab == "ustawienia":
            self.refresh_settings_view()
        elif tab == "notatki":
            self.refresh_notes_view()

    def create_control_view(self):
        frame = self.make_panel(self.content, "CONTROL")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        grid = ctk.CTkFrame(frame, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="new", padx=self.scale_hud(18), pady=self.hud_pad((8, 12)))
        for column in range(3):
            grid.grid_columnconfigure(column, weight=1)

        ctk.CTkLabel(
            grid,
            text="URUCHAMIANIE",
            text_color=CYAN,
            font=self.ui_font(10, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=self.scale_hud(8), pady=self.hud_pad((2, 4)))
        ctk.CTkLabel(
            grid,
            text="NARZEDZIA",
            text_color=CYAN,
            font=self.ui_font(10, "bold"),
        ).grid(row=2, column=0, columnspan=3, sticky="w", padx=self.scale_hud(8), pady=self.hud_pad((14, 4)))

        actions = [
            ("Start Processor", self.start_processor, PURPLE),
            ("Start Backend", self.start_backend, CYAN),
            ("Start Agent", self.start_agent, BLUE),
            ("Połącz telefon", self.open_pairing, PURPLE),
            ("Skanuj aplikacje", self.scan_apps, PURPLE),
            ("Odśwież status", self.refresh_status, CYAN),
        ]
        for index, (label, command, color) in enumerate(actions):
            button = self.make_button(grid, label, command, border_color=color, width=210, height=42)
            button.grid(row=(index // 3) * 2 + 1, column=index % 3, padx=self.scale_hud(8), pady=self.scale_hud(6), sticky="ew")
            if label == "Skanuj aplikacje":
                self.scan_apps_button = button
                self.scan_app_buttons.append(button)
            if label == "Odśwież status":
                self.refresh_button = button

        self.control_status_frame = ctk.CTkScrollableFrame(
            frame,
            fg_color="#07101d",
            border_color=LINE,
            border_width=1,
            corner_radius=self.scale_hud(8),
        )
        self.control_status_frame.grid(row=2, column=0, sticky="nsew", padx=self.scale_hud(18), pady=self.hud_pad((0, 18)))
        frame.grid_rowconfigure(2, weight=1)
        self.control_status_labels = {}
        for row, name in enumerate([
            "Backend",
            "Hub",
            "Processor / LLM",
            "Agent PC",
            "Telefon",
            "Model",
            "Device ID",
            "API Token",
            "LM Studio",
        ]):
            self.add_control_status_row(row, name, "Nieznany")
        return frame

    def add_control_status_row(self, row, name, value):
        item = ctk.CTkFrame(self.control_status_frame, fg_color=PANEL, border_color=LINE, border_width=1, corner_radius=self.scale_hud(8))
        item.grid(row=row, column=0, sticky="ew", padx=self.scale_hud(10), pady=self.scale_hud(5))
        item.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(
            item,
            text=name.upper(),
            text_color=MUTED,
            font=self.ui_font(10, "bold"),
        ).grid(row=0, column=0, padx=self.scale_hud(10), pady=self.scale_hud(8), sticky="w")
        value_label = ctk.CTkLabel(
            item,
            text=value,
            text_color=TEXT,
            font=self.ui_font(10),
        )
        value_label.grid(row=0, column=1, padx=self.scale_hud(10), pady=self.scale_hud(8), sticky="e")
        self.control_status_labels[name] = value_label

    def create_apps_view(self):
        frame = self.make_panel(self.content, "APLIKACJE")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(4, weight=1)

        tools = ctk.CTkFrame(frame, fg_color="transparent")
        tools.grid(row=1, column=0, sticky="ew", padx=self.scale_hud(14), pady=self.hud_pad((4, 10)))
        tools.grid_columnconfigure(0, weight=1)

        self.app_search_entry = ctk.CTkEntry(
            tools,
            textvariable=self.app_search,
            placeholder_text="Szukaj aplikacji...",
            fg_color=PANEL_2,
            text_color=TEXT,
            border_color=CYAN,
            border_width=1,
            corner_radius=self.scale_hud(8),
            font=self.ui_font(11),
        )
        self.bind_ctrl_backspace(self.app_search_entry)
        self.app_search_entry.grid(row=0, column=0, sticky="ew", padx=self.hud_pad((0, 10)))
        self.app_search.trace_add("write", lambda *_: self.reset_apps_page_and_render())

        self.filter_menu = ctk.CTkOptionMenu(
            tools,
            values=["Wszystkie", "Wykryte", "Ręczne", "Ukryte"],
            variable=self.app_filter,
            command=lambda _: self.reset_apps_page_and_render(),
            fg_color=PANEL_2,
            button_color=BLUE,
            button_hover_color=PURPLE,
            dropdown_fg_color=PANEL,
            text_color=TEXT,
            width=self.scale_hud(140),
        )
        self.filter_menu.grid(row=0, column=1, padx=self.hud_pad((0, 10)))

        scan_button = self.make_button(tools, "Skanuj aplikacje", self.scan_apps, border_color=PURPLE, width=150)
        scan_button.grid(row=0, column=2, sticky="e", padx=self.hud_pad((0, 10)))
        self.scan_app_buttons.append(scan_button)
        self.clean_apps_button = self.make_button(
            tools,
            "Wyczyść listę",
            self.clean_apps,
            border_color=DANGER,
            width=140,
        )
        self.clean_apps_button.grid(row=0, column=3, sticky="e")

        self.manual_form = self.create_manual_app_form(frame)
        self.manual_form.grid(row=2, column=0, sticky="ew", padx=self.scale_hud(14), pady=self.hud_pad((0, 10)))

        self.apps_count_label = ctk.CTkLabel(
            frame,
            text="0 aplikacji",
            text_color=MUTED,
            font=self.ui_font(10),
        )
        self.apps_count_label.grid(row=3, column=0, sticky="w", padx=self.scale_hud(14), pady=self.hud_pad((0, 6)))

        pager = ctk.CTkFrame(frame, fg_color="transparent")
        pager.grid(row=5, column=0, sticky="ew", padx=self.scale_hud(14), pady=self.hud_pad((0, 14)))
        pager.grid_columnconfigure(1, weight=1)
        self.prev_apps_button = self.make_button(
            pager,
            "Poprzednia",
            self.previous_apps_page,
            border_color=BLUE,
            width=120,
            height=30,
        )
        self.prev_apps_button.grid(row=0, column=0, sticky="w")
        self.apps_page_label = ctk.CTkLabel(
            pager,
            text="Strona 0/0",
            text_color=MUTED,
            font=self.ui_font(10, "bold"),
        )
        self.apps_page_label.grid(row=0, column=1, sticky="ew")
        self.next_apps_button = self.make_button(
            pager,
            "Następna",
            self.next_apps_page,
            border_color=BLUE,
            width=120,
            height=30,
        )
        self.next_apps_button.grid(row=0, column=2, sticky="e")

        self.apps_grid = ctk.CTkScrollableFrame(
            frame,
            fg_color="#07101d",
            border_color="#123249",
            border_width=1,
            corner_radius=self.scale_hud(8),
        )
        self.apps_grid.grid(row=4, column=0, sticky="nsew", padx=self.scale_hud(14), pady=self.hud_pad((0, 14)))
        return frame

    def create_manual_app_form(self, parent):
        form = ctk.CTkFrame(parent, fg_color=PANEL_2, border_color=LINE, border_width=1, corner_radius=self.scale_hud(8))
        form.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            form,
            text="DODAJ APLIKACJĘ RĘCZNIE",
            text_color=CYAN,
            font=self.ui_font(10, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=self.scale_hud(12), pady=self.hud_pad((10, 6)))

        self.make_button(form, "Wybierz plik", self.choose_manual_app_file, border_color=BLUE, width=118, height=30).grid(
            row=1, column=0, sticky="w", padx=self.hud_pad((12, 10)), pady=self.hud_pad((0, 10))
        )
        ctk.CTkLabel(
            form,
            textvariable=self.manual_selected_text,
            text_color=MUTED,
            anchor="w",
            font=self.ui_font(10),
        ).grid(
            row=1, column=1, sticky="ew", padx=self.hud_pad((0, 10)), pady=self.hud_pad((0, 10))
        )
        self.make_button(form, "Zapisz", self.save_manual_app, border_color=PURPLE, width=118, height=30).grid(
            row=1, column=2, sticky="e", padx=self.hud_pad((0, 12)), pady=self.hud_pad((0, 10))
        )
        return form

    def make_entry(self, parent, variable, placeholder):
        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            placeholder_text=placeholder,
            fg_color=PANEL,
            text_color=TEXT,
            border_color=CYAN,
            border_width=1,
            corner_radius=self.scale_hud(8),
            font=self.ui_font(10),
        )
        return self.bind_ctrl_backspace(entry)

    def create_settings_view(self):
        frame = self.make_panel(self.content, "USTAWIENIA")
        frame.grid_rowconfigure(1, weight=1)
        self.settings_grid = ctk.CTkScrollableFrame(
            frame,
            fg_color="#07101d",
            border_color=LINE,
            border_width=1,
            corner_radius=self.scale_hud(8),
        )
        self.settings_grid.grid(row=1, column=0, sticky="nsew", padx=self.scale_hud(16), pady=self.scale_hud(16))
        self.settings_grid.grid_columnconfigure(0, weight=1)
        return frame

    def create_chat_view(self):
        frame = self.make_panel(self.content, "CHAT")
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        self.chat_box = ctk.CTkTextbox(
            frame,
            fg_color="#07101d",
            text_color=TEXT,
            border_color=LINE,
            border_width=1,
            corner_radius=self.scale_hud(8),
            font=self.ui_font(12),
        )
        self.chat_box.grid(row=1, column=0, sticky="nsew", padx=self.scale_hud(14), pady=self.hud_pad((4, 12)))
        self.chat_box.configure(state="disabled")

        command_bar = ctk.CTkFrame(frame, fg_color="transparent")
        command_bar.grid(row=2, column=0, sticky="ew", padx=self.scale_hud(14), pady=self.hud_pad((0, 14)))
        command_bar.grid_columnconfigure(0, weight=1)
        chat_entry = ctk.CTkEntry(
            command_bar,
            textvariable=self.chat_input,
            placeholder_text="Wiadomość lub komenda...",
            fg_color=PANEL_2,
            text_color=TEXT,
            border_color=CYAN,
            border_width=1,
            corner_radius=self.scale_hud(8),
            font=self.ui_font(12),
            height=self.scale_hud(40),
        )
        self.bind_ctrl_backspace(chat_entry)
        chat_entry.grid(row=0, column=0, sticky="ew", padx=self.hud_pad((0, 10)))
        chat_entry.bind("<Return>", lambda _event: self.send_chat_message())
        self.make_button(command_bar, "Wyślij", self.send_chat_message, border_color=CYAN, width=110, height=40).grid(
            row=0, column=1, sticky="e"
        )
        return frame

    def create_notes_view(self):
        frame = self.make_panel(self.content, "NOTATKI")
        frame.grid_rowconfigure(2, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_columnconfigure(1, weight=2)

        tools = ctk.CTkFrame(frame, fg_color="transparent")
        tools.grid(row=1, column=0, columnspan=2, sticky="ew", padx=self.scale_hud(14), pady=self.hud_pad((4, 10)))
        self.make_button(tools, "Nowa notatka", self.show_new_note_form, border_color=PURPLE, width=150).grid(
            row=0, column=0, sticky="w"
        )

        self.note_form = ctk.CTkFrame(frame, fg_color=PANEL_2, border_color=LINE, border_width=1, corner_radius=self.scale_hud(8))
        self.note_form.grid_columnconfigure(0, weight=1)
        self.note_title_entry = self.make_entry(self.note_form, self.note_title_var, "Tytuł")
        self.note_title_entry.grid(row=0, column=0, sticky="ew", padx=self.scale_hud(10), pady=self.hud_pad((10, 6)))
        self.note_content_box = ctk.CTkTextbox(
            self.note_form,
            fg_color=PANEL,
            text_color=TEXT,
            border_color=CYAN,
            border_width=1,
            corner_radius=self.scale_hud(8),
            height=self.scale_hud(100),
            font=self.ui_font(11),
        )
        self.bind_ctrl_backspace(self.note_content_box)
        self.note_content_box.grid(row=1, column=0, sticky="ew", padx=self.scale_hud(10), pady=self.scale_hud(6))
        note_buttons = ctk.CTkFrame(self.note_form, fg_color="transparent")
        note_buttons.grid(row=2, column=0, sticky="e", padx=self.scale_hud(10), pady=self.hud_pad((4, 10)))
        self.make_button(note_buttons, "Zapisz", self.save_new_note, border_color=PURPLE, width=100, height=30).grid(
            row=0, column=0, padx=self.hud_pad((0, 8))
        )
        self.make_button(note_buttons, "Anuluj", self.hide_new_note_form, border_color=BLUE, width=100, height=30).grid(
            row=0, column=1
        )
        self.note_form.grid(row=2, column=0, columnspan=2, sticky="ew", padx=self.scale_hud(14), pady=self.hud_pad((0, 10)))
        self.note_form.grid_remove()

        self.notes_list = ctk.CTkScrollableFrame(
            frame,
            fg_color="#07101d",
            border_color="#123249",
            border_width=1,
            corner_radius=self.scale_hud(8),
        )
        self.notes_list.grid(row=3, column=0, sticky="nsew", padx=self.hud_pad((14, 8)), pady=self.hud_pad((0, 14)))
        self.note_details = ctk.CTkFrame(frame, fg_color="#07101d", border_color=LINE, border_width=1, corner_radius=self.scale_hud(8))
        self.note_details.grid(row=3, column=1, sticky="nsew", padx=self.hud_pad((8, 14)), pady=self.hud_pad((0, 14)))
        self.note_details.grid_columnconfigure(0, weight=1)
        self.note_details.grid_rowconfigure(1, weight=1)
        self.note_detail_title = ctk.CTkLabel(
            self.note_details,
            text="Wybierz notatkę",
            text_color=TEXT,
            font=self.ui_font(13, "bold"),
        )
        self.note_detail_title.grid(row=0, column=0, sticky="w", padx=self.scale_hud(12), pady=self.hud_pad((12, 6)))
        self.note_detail_content = ctk.CTkTextbox(
            self.note_details,
            fg_color=PANEL,
            text_color=TEXT,
            border_color=LINE,
            border_width=1,
            corner_radius=self.scale_hud(8),
            font=self.ui_font(11),
        )
        self.note_detail_content.grid(row=1, column=0, sticky="nsew", padx=self.scale_hud(12), pady=self.scale_hud(6))
        self.note_detail_content.configure(state="disabled")
        footer = ctk.CTkFrame(self.note_details, fg_color="transparent")
        footer.grid(row=2, column=0, sticky="ew", padx=self.scale_hud(12), pady=self.hud_pad((4, 12)))
        footer.grid_columnconfigure(0, weight=1)
        self.note_detail_date = ctk.CTkLabel(footer, text="", text_color=MUTED, font=self.ui_font(10))
        self.note_detail_date.grid(row=0, column=0, sticky="w")
        self.make_button(footer, "Usuń", self.delete_selected_note, border_color=DANGER, width=90, height=30).grid(
            row=0, column=1, sticky="e"
        )
        return frame

    def refresh_settings_view(self):
        for widget in self.settings_grid.winfo_children():
            widget.destroy()

        row = 0
        row = self.add_settings_section(row, "POŁĄCZENIE")
        row = self.add_setting_entry(row, "Backend URL", self.backend_url)
        row = self.add_setting_entry(row, "API Token", self.api_token, show="*")
        row = self.add_setting_entry(row, "Device ID", self.device_id)
        row = self.add_settings_buttons(
            row,
            [
                ("Odśwież połączenie", self.refresh_status, CYAN),
                ("Połącz telefon / QR", self.open_pairing, PURPLE),
            ],
        )

        row = self.add_settings_section(row, "WYGLĄD")
        row = self.add_scale_row(row, "Text Scale", self.text_scale, 0.05)
        row = self.add_scale_row(row, "HUD Scale", self.hud_scale, 0.05)
        row = self.add_checkbox_row(row, "Show System Status", self.show_status_panel, self.apply_panel_visibility)
        row = self.add_checkbox_row(row, "Show Console Log", self.show_console_log, self.apply_panel_visibility)

        row = self.add_settings_section(row, "GŁOS")
        row = self.add_checkbox_row(row, "voice_enabled", self.voice_enabled)
        row = self.add_setting_entry(row, "voice_language", self.voice_language)
        row = self.add_setting_entry(row, "voice_rate", self.voice_rate)
        row = self.add_setting_entry(row, "voice_pitch", self.voice_pitch)
        row = self.add_checkbox_row(row, "microphone_enabled", self.microphone_enabled)
        row = self.add_checkbox_row(row, "PTT mode", self.ptt_mode)
        row = self.add_settings_buttons(row, [("Test głosu", self.test_voice, BLUE)])

        row = self.add_settings_buttons(
            row,
            [
                ("Zapisz ustawienia", self.save_settings, PURPLE),
                ("Reset ustawień", self.reset_settings, DANGER),
            ],
        )

    def add_settings_section(self, row, title):
        ctk.CTkLabel(
            self.settings_grid,
            text=title,
            text_color=CYAN,
            font=self.ui_font(12, "bold"),
        ).grid(row=row, column=0, sticky="w", padx=self.scale_hud(12), pady=self.hud_pad((14, 8)))
        return row + 1

    def add_setting_entry(self, row, label, variable, show=None):
        line = ctk.CTkFrame(self.settings_grid, fg_color="transparent")
        line.grid(row=row, column=0, sticky="ew", padx=self.scale_hud(12), pady=self.scale_hud(5))
        line.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(line, text=label, text_color=MUTED, font=self.ui_font(10, "bold")).grid(
            row=0, column=0, sticky="w", padx=self.hud_pad((0, 12))
        )
        entry = ctk.CTkEntry(
            line,
            textvariable=variable,
            show=show,
            fg_color=PANEL,
            text_color=TEXT,
            border_color=CYAN,
            border_width=1,
            corner_radius=self.scale_hud(8),
            font=self.ui_font(10),
        )
        self.bind_ctrl_backspace(entry)
        entry.grid(row=0, column=1, sticky="ew")
        return row + 1

    def add_checkbox_row(self, row, label, variable, command=None):
        checkbox = ctk.CTkCheckBox(
            self.settings_grid,
            text=label,
            variable=variable,
            command=command,
            fg_color=PURPLE,
            hover_color=BLUE,
            border_color=CYAN,
            text_color=TEXT,
            font=self.ui_font(10, "bold"),
        )
        checkbox.grid(row=row, column=0, sticky="w", padx=self.scale_hud(12), pady=self.scale_hud(6))
        return row + 1

    def add_scale_row(self, row, label, variable, step):
        line = ctk.CTkFrame(self.settings_grid, fg_color="transparent")
        line.grid(row=row, column=0, sticky="ew", padx=self.scale_hud(12), pady=self.scale_hud(5))
        line.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(line, text=label, text_color=MUTED, font=self.ui_font(10, "bold")).grid(
            row=0, column=0, padx=self.hud_pad((0, 10)), sticky="w"
        )
        self.make_button(line, "-", lambda var=variable, s=step: self.adjust_scale(var, -s), border_color=BLUE, width=34, height=28).grid(
            row=0, column=1, sticky="e", padx=self.hud_pad((0, 6))
        )
        scale_entry = ctk.CTkEntry(
            line,
            textvariable=variable,
            fg_color=PANEL,
            text_color=TEXT,
            border_color=CYAN,
            border_width=1,
            width=self.scale_hud(80),
            corner_radius=self.scale_hud(8),
            font=self.ui_font(10),
        )
        self.bind_ctrl_backspace(scale_entry)
        scale_entry.bind("<Return>", lambda event, var=variable: self.commit_scale_value(var, event), add="+")
        scale_entry.bind("<KP_Enter>", lambda event, var=variable: self.commit_scale_value(var, event), add="+")
        scale_entry.bind("<FocusOut>", lambda event, var=variable: self.commit_scale_value(var, event), add="+")
        scale_entry.grid(row=0, column=2, sticky="e")
        self.make_button(line, "+", lambda var=variable, s=step: self.adjust_scale(var, s), border_color=BLUE, width=34, height=28).grid(
            row=0, column=3, sticky="e", padx=self.hud_pad((6, 0))
        )
        return row + 1

    def add_settings_buttons(self, row, buttons):
        line = ctk.CTkFrame(self.settings_grid, fg_color="transparent")
        line.grid(row=row, column=0, sticky="w", padx=self.scale_hud(12), pady=self.scale_hud(8))
        for column, (label, command, color) in enumerate(buttons):
            self.make_button(line, label, command, border_color=color, width=160, height=32).grid(
                row=0, column=column, padx=self.hud_pad((0, 8))
            )
        return row + 1

    def refresh_notes_view(self):
        for widget in self.notes_list.winfo_children():
            widget.destroy()
        try:
            notes = load_notes()
        except Exception as error:
            self.log(f"Błąd notatek: {error}")
            notes = []

        if not notes:
            ctk.CTkLabel(self.notes_list, text="Brak notatek", text_color=MUTED).grid(
                row=0, column=0, padx=self.scale_hud(14), pady=self.scale_hud(14), sticky="w"
            )
            return

        for row, note in enumerate(notes):
            title = note.get("title") or "Bez tytułu"
            button = self.make_button(
                self.notes_list,
                str(title),
                lambda item=note: self.show_note_details(item),
                border_color=CYAN,
                width=220,
                height=34,
            )
            button.grid(row=row, column=0, sticky="ew", padx=self.scale_hud(10), pady=self.scale_hud(5))

    def show_new_note_form(self):
        self.note_title_var.set("")
        self.note_content_box.configure(state="normal")
        self.note_content_box.delete("1.0", "end")
        self.note_form.grid()

    def hide_new_note_form(self):
        self.note_form.grid_remove()

    def save_new_note(self):
        title = self.note_title_var.get().strip()
        content = self.note_content_box.get("1.0", "end-1c").strip()
        if not content:
            self.log("Brakuje treści notatki.")
            return
        try:
            result = create_note(content, title)
            if result == "saved":
                self.log(f"Zapisano notatkę: {title or 'bez tytułu'}")
                self.hide_new_note_form()
                self.refresh_notes_view()
            else:
                self.log("Nie udało się zapisać notatki.")
        except Exception as error:
            self.log(f"Błąd zapisu notatki: {error}")

    def show_note_details(self, note):
        self.note_selected = note
        self.note_detail_title.configure(text=str(note.get("title") or "Bez tytułu"))
        self.note_detail_content.configure(state="normal")
        self.note_detail_content.delete("1.0", "end")
        self.note_detail_content.insert("1.0", str(note.get("content") or ""))
        self.note_detail_content.configure(state="disabled")
        self.note_detail_date.configure(text=str(note.get("created_at") or "brak daty"))

    def delete_selected_note(self):
        if not self.note_selected:
            self.log("Nie wybrano notatki.")
            return
        try:
            result = delete_note(self.note_selected.get("path"))
            if result in {"deleted", "ok", "removed"}:
                self.log("Usunięto notatkę.")
            else:
                self.log(f"Wynik usuwania notatki: {result}")
            self.note_selected = None
            self.note_detail_title.configure(text="Wybierz notatkę")
            self.note_detail_content.configure(state="normal")
            self.note_detail_content.delete("1.0", "end")
            self.note_detail_content.configure(state="disabled")
            self.note_detail_date.configure(text="")
            self.refresh_notes_view()
        except Exception as error:
            self.log(f"Błąd usuwania notatki: {error}")

    def adjust_scale(self, variable, delta):
        current_tab = self.active_tab
        minimum, maximum, _key, fallback, last_attr = self.scale_meta(variable)
        value = self.parse_scale_value(variable.get(), getattr(self, last_attr, fallback), minimum, maximum)
        value = max(minimum, min(maximum, value + delta))
        variable.set(f"{value:.2f}")
        setattr(self, last_attr, value)
        self.save_scale_settings()
        self.apply_scale(current_tab)

    def scale_meta(self, variable):
        if variable is self.hud_scale:
            return 0.6, 1.5, "hud_scale", 1.15, "last_valid_hud_scale"
        return 0.6, 1.8, "text_scale", 1.0, "last_valid_text_scale"

    def parse_scale_value(self, raw_value, fallback, minimum, maximum):
        try:
            value = float(str(raw_value).strip().replace(",", "."))
        except (TypeError, ValueError):
            value = fallback
        return max(minimum, min(maximum, value))

    def commit_scale_value(self, variable, event=None, apply_ui=True):
        current_tab = self.active_tab
        minimum, maximum, _key, fallback, last_attr = self.scale_meta(variable)
        old_value = getattr(self, last_attr, fallback)
        value = self.parse_scale_value(variable.get(), old_value, minimum, maximum)
        variable.set(f"{value:.2f}")
        setattr(self, last_attr, value)
        self.save_scale_settings()
        if apply_ui:
            self.apply_scale(current_tab)
            self.restore_active_tab(current_tab)
        return "break" if event is not None and getattr(event, "keysym", "") in {"Return", "KP_Enter"} else None

    def save_scale_settings(self):
        config = load_config()
        config["text_scale"] = self.parse_scale_value(self.text_scale.get(), self.last_valid_text_scale, 0.6, 1.8)
        config["hud_scale"] = self.parse_scale_value(self.hud_scale.get(), self.last_valid_hud_scale, 0.6, 1.5)
        save_config(config)

    def apply_scale(self, current_tab=None):
        current_tab = current_tab or self.active_tab
        self.last_valid_text_scale = self.parse_scale_value(self.text_scale.get(), self.last_valid_text_scale, 0.6, 1.8)
        self.last_valid_hud_scale = self.parse_scale_value(self.hud_scale.get(), self.last_valid_hud_scale, 0.6, 1.5)
        self.text_scale.set(f"{self.last_valid_text_scale:.2f}")
        self.hud_scale.set(f"{self.last_valid_hud_scale:.2f}")
        self.rebuild_scaled_ui(current_tab)

    def restore_active_tab(self, tab):
        if tab in self.views and self.active_tab != tab:
            self.switch_tab(tab)

    def apply_panel_visibility(self):
        if hasattr(self, "status_panel"):
            if self.show_status_panel.get():
                self.status_panel.grid()
            else:
                self.status_panel.grid_remove()
        if hasattr(self, "log_panel"):
            if self.show_console_log.get():
                self.log_panel.grid()
            else:
                self.log_panel.grid_remove()

    def save_settings(self):
        current_tab = self.active_tab
        self.commit_scale_value(self.text_scale, apply_ui=False)
        self.commit_scale_value(self.hud_scale, apply_ui=False)
        config = load_config()
        config.update(
            {
                "backend_url": self.backend_url.get().strip() or "http://127.0.0.1:8000",
                "api_token": self.api_token.get(),
                "device_id": self.device_id.get().strip() or "local-pc",
                "text_scale": self.parse_scale_value(self.text_scale.get(), self.last_valid_text_scale, 0.6, 1.8),
                "hud_scale": self.parse_scale_value(self.hud_scale.get(), self.last_valid_hud_scale, 0.6, 1.5),
                "show_system_status": bool(self.show_status_panel.get()),
                "show_console_log": bool(self.show_console_log.get()),
                "voice_enabled": bool(self.voice_enabled.get()),
                "voice_language": self.voice_language.get().strip() or "pl-PL",
                "voice_rate": self.voice_rate.get().strip(),
                "voice_pitch": self.voice_pitch.get().strip(),
                "microphone_enabled": bool(self.microphone_enabled.get()),
                "ptt_mode": bool(self.ptt_mode.get()),
            }
        )
        try:
            save_config(config)
            self.apply_panel_visibility()
            self.apply_scale(current_tab)
            self.restore_active_tab(current_tab)
            self.log("Zapisano ustawienia.")
        except Exception as error:
            self.log(f"Błąd zapisu ustawień: {error}")

    def reset_settings(self):
        current_tab = self.active_tab
        self.backend_url.set("http://127.0.0.1:8000")
        self.api_token.set("")
        self.device_id.set("local-pc")
        self.last_valid_text_scale = 1.0
        self.last_valid_hud_scale = 1.15
        self.text_scale.set("1.00")
        self.hud_scale.set("1.15")
        self.show_status_panel.set(True)
        self.show_console_log.set(True)
        self.voice_enabled.set(True)
        self.voice_language.set("pl-PL")
        self.voice_rate.set("+0%")
        self.voice_pitch.set("+0Hz")
        self.microphone_enabled.set(True)
        self.ptt_mode.set(True)
        self.apply_panel_visibility()
        self.restore_active_tab(current_tab)
        self.log("Zresetowano ustawienia w formularzu.")

    def test_voice(self):
        self.log("Test głosu: nieobsługiwane w Control Center.")

    def safe_float(self, value, fallback):
        try:
            return float(value)
        except ValueError:
            return fallback

    def load_apps_view_once(self):
        if self.apps_loaded:
            self.render_apps_page()
            return
        self.reload_apps_view()

    def reload_apps_view(self):
        if self.apps_loading:
            return
        self.apps_loading = True
        self.apps_count_label.configure(text="Wczytuję aplikacje...")
        self.clear_apps_grid("Wczytuję aplikacje...")
        threading.Thread(target=self._load_apps_worker, daemon=True).start()

    def _load_apps_worker(self):
        try:
            raw_apps = load_apps_raw()
            if not isinstance(raw_apps, dict):
                raise ValueError("apps.json nie zawiera obiektu JSON")
            records = self.normalize_app_records(raw_apps)
            self.after(0, lambda: self.on_apps_loaded(records))
        except Exception as error:
            self.after(0, lambda err=error: self.on_apps_load_failed(err))

    def normalize_app_records(self, raw_apps):
        records = []
        for key, entry in raw_apps.items():
            try:
                if not isinstance(key, str) or not key.strip():
                    continue
                label = app_label_from_entry(entry, key)
                records.append(
                    {
                        "key": key,
                        "entry": entry,
                        "label": str(label or key),
                        "type": entry_type(entry),
                        "path": entry_launch_path(entry),
                        "hidden": is_hidden(entry),
                        "discovered": is_discovered(entry),
                    }
                )
            except Exception as error:
                self.after(0, lambda app_key=key, err=error: self.log(f"Pominięto aplikację {app_key}: {err}"))
        return sorted(records, key=lambda record: record["label"].lower())

    def on_apps_loaded(self, records):
        self.apps_cache = records
        self.apps_loaded = True
        self.apps_loading = False
        self.apps_page = 0
        self.log(f"Załadowano {len(records)} aplikacji")
        self.render_apps_page()

    def on_apps_load_failed(self, error):
        self.apps_cache = []
        self.apps_loaded = True
        self.apps_loading = False
        self.apps_page = 0
        self.log(f"Nie udało się wczytać apps.json: {error}")
        self.apps_count_label.configure(text="Nie udało się wczytać apps.json")
        self.clear_apps_grid("Brak aplikacji")
        self.update_apps_pager(0, 0)

    def reset_apps_page_and_render(self):
        self.apps_page = 0
        if self.apps_loaded:
            self.render_apps_page()

    def filtered_apps(self):
        query = self.app_search.get().strip().lower()
        filter_name = self.app_filter.get()
        items = []
        for record in self.apps_cache:
            if filter_name != "Ukryte" and record["hidden"]:
                continue
            if filter_name == "Wykryte" and not record["discovered"]:
                continue
            if filter_name == "Ręczne" and record["discovered"]:
                continue
            if filter_name == "Ukryte" and not record["hidden"]:
                continue
            if query and query not in f"{record['key']} {record['label']}".lower():
                continue
            items.append(record)
        return items

    def render_apps_page(self):
        if not hasattr(self, "apps_grid"):
            return

        items = self.filtered_apps()
        total = len(items)
        total_pages = max(1, (total + self.apps_per_page - 1) // self.apps_per_page)
        self.apps_page = min(max(self.apps_page, 0), total_pages - 1)
        start = self.apps_page * self.apps_per_page
        page_items = items[start : start + self.apps_per_page]

        self.clear_apps_grid()
        self.apps_count_label.configure(text=f"Załadowano {len(self.apps_cache)} aplikacji, widoczne {total}")
        self.update_apps_pager(total, total_pages)

        if not page_items:
            self.clear_apps_grid("Brak aplikacji")
            return

        for column in range(3):
            self.apps_grid.grid_columnconfigure(column, weight=1, uniform="apps")

        for index, record in enumerate(page_items):
            self.add_app_card(index, record)

    def clear_apps_grid(self, message=None):
        for widget in self.apps_grid.winfo_children():
            widget.destroy()
        if message:
            ctk.CTkLabel(self.apps_grid, text=message, text_color=MUTED).grid(
                row=0, column=0, padx=self.scale_hud(14), pady=self.scale_hud(14), sticky="w"
            )

    def update_apps_pager(self, total, total_pages):
        if total == 0:
            label = "Strona 0/0"
        else:
            label = f"Strona {self.apps_page + 1}/{total_pages}"
        self.apps_page_label.configure(text=label)
        self.prev_apps_button.configure(state="normal" if total > 0 and self.apps_page > 0 else "disabled")
        self.next_apps_button.configure(
            state="normal" if total > 0 and self.apps_page < total_pages - 1 else "disabled"
        )

    def previous_apps_page(self):
        if self.apps_page > 0:
            self.apps_page -= 1
            self.render_apps_page()

    def next_apps_page(self):
        total = len(self.filtered_apps())
        total_pages = max(1, (total + self.apps_per_page - 1) // self.apps_per_page)
        if self.apps_page < total_pages - 1:
            self.apps_page += 1
            self.render_apps_page()

    def add_app_card(self, index, record):
        key = record["key"]
        label = record["label"]
        row = index // 3
        column = index % 3
        card = ctk.CTkFrame(self.apps_grid, fg_color=PANEL, border_color=LINE, border_width=1, corner_radius=self.scale_hud(8))
        card.grid(row=row, column=column, padx=self.scale_hud(8), pady=self.scale_hud(8), sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=str(label),
            text_color=TEXT,
            anchor="w",
            font=self.ui_font(12, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=self.scale_hud(12), pady=self.hud_pad((12, 4)))
        ctk.CTkLabel(
            card,
            text=f"type: {record['type']}",
            text_color=CYAN if record["discovered"] else PURPLE,
            anchor="w",
            font=self.ui_font(9, "bold"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=self.scale_hud(12))
        ctk.CTkLabel(
            card,
            text=short_path(record["path"]),
            text_color=MUTED,
            anchor="w",
            wraplength=210,
            font=self.ui_font(9),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=self.scale_hud(12), pady=self.hud_pad((4, 10)))

        self.make_button(card, "Otwórz", lambda target=key: self.open_app_action(target), border_color=CYAN, width=96, height=30).grid(
            row=3, column=0, sticky="w", padx=self.hud_pad((12, 4)), pady=self.hud_pad((0, 12))
        )
        self.make_button(card, "Zamknij", lambda target=key: self.close_app_action(target), border_color=DANGER, width=96, height=30).grid(
            row=3, column=1, sticky="e", padx=self.hud_pad((4, 12)), pady=self.hud_pad((0, 12))
        )

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("1.0", f"[{timestamp}] {message}\n")
        lines = self.log_box.get("1.0", "end-1c").splitlines()
        if len(lines) > 120:
            self.log_box.delete("121.0", "end")
        self.log_box.configure(state="disabled")

    def add_chat_message(self, author, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"[{timestamp}] {author}: {message}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def send_chat_message(self):
        message = self.chat_input.get().strip()
        if not message:
            return
        self.chat_input.set("")
        self.add_chat_message("Ty", message)
        threading.Thread(target=self._send_chat_worker, args=(message,), daemon=True).start()

    def _send_chat_worker(self, message):
        base_url = self.backend_url.get().strip().rstrip("/") or "http://127.0.0.1:8000"
        headers = self.auth_headers()
        try:
            status, data = post_json(
                f"{base_url}/process-text",
                {"text": message, "device_id": self.device_id.get().strip() or "local-pc"},
                headers=headers,
            )
            response = data.get("response") if isinstance(data, dict) else None
            if status == 200 and response:
                self.after(0, lambda: self.add_chat_message("Jarvis", str(response)))
                return
        except Exception:
            pass

        try:
            status, data = post_json(f"{base_url}/chat", {"message": message}, headers=headers)
            response = data.get("response") if isinstance(data, dict) else None
            if status == 200 and response:
                self.after(0, lambda: self.add_chat_message("Jarvis", str(response)))
                return
            self.after(0, lambda: self.add_chat_message("System", "Brak odpowiedzi backendu."))
        except urllib.error.HTTPError as error:
            text = "Unauthorized" if error.code == 401 else f"Błąd HTTP: {error.code}"
            self.after(0, lambda: self.add_chat_message("System", text))
        except Exception:
            self.after(0, lambda: self.add_chat_message("System", "Backend offline lub nieobsługiwane."))

    def set_status(self, name, state, detail=None):
        if name not in self.status_labels:
            return
        color = SUCCESS if state == "Online" else DANGER if state == "Offline" else UNKNOWN
        self.status_dots[name].configure(text_color=color)
        self.status_labels[name].configure(text=detail or state, text_color=TEXT)

    def refresh_status(self):
        if hasattr(self, "refresh_button"):
            self.refresh_button.configure(state="disabled", text="Sprawdzam...")
        threading.Thread(target=self._refresh_status_worker, daemon=True).start()

    def _refresh_status_worker(self):
        statuses = {
            "LM Studio": self.check_lm_studio(),
            "Processor": self.check_processor(),
            "Backend": self.check_backend(),
            "Agent": self.check_agent(),
            "Telefon": self.check_phone(),
        }
        config = load_config()
        self.after(0, lambda: self.apply_statuses(statuses, config))

    def apply_statuses(self, statuses, config):
        for name, (state, detail) in statuses.items():
            self.set_status(name, state, detail)
        self.set_status("Model", "Unknown", str(config.get("model") or "local-model"))
        self.set_status("Device ID", "Unknown", str(config.get("device_id") or "local-pc"))
        self.update_control_statuses(statuses, config)
        self.log("Status odświeżony")
        if hasattr(self, "refresh_button"):
            self.refresh_button.configure(state="normal", text="Odśwież status")

    def auth_headers(self):
        token = self.api_token.get() or load_config().get("api_token") or ""
        return {"X-Jarvis-Token": token} if token else {}

    def backend_api_url(self, path):
        base_url = self.backend_url.get().strip().rstrip("/") or "http://127.0.0.1:8000"
        return f"{base_url}{path}"

    def update_control_statuses(self, statuses, config):
        if not hasattr(self, "control_status_labels"):
            return
        mapping = {
            "Backend": statuses.get("Backend", ("Offline", "Offline"))[1],
            "Hub": self.backend_url.get().strip() or "http://127.0.0.1:8000",
            "Processor / LLM": statuses.get("Processor", ("Offline", "Offline"))[1],
            "Agent PC": statuses.get("Agent", ("Offline", "Offline"))[1],
            "Telefon": statuses.get("Telefon", ("Offline", "Offline"))[1],
            "Model": str(config.get("model") or "local-model"),
            "Device ID": self.device_id.get().strip() or str(config.get("device_id") or "local-pc"),
            "API Token": "••••••••" if (self.api_token.get() or config.get("api_token")) else "brak",
            "LM Studio": statuses.get("LM Studio", ("Offline", "Offline"))[1],
        }
        for name, value in mapping.items():
            if name in self.control_status_labels:
                self.control_status_labels[name].configure(text=str(value))

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
            status, data = request_json(self.backend_api_url("/status"))
            if status == 200:
                return "Online", str(data.get("status") or "Online")
        except Exception:
            pass
        return "Offline", "Offline"

    def check_agent(self):
        try:
            status, data = request_json(self.backend_api_url("/agents"), headers=self.auth_headers())
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

    def check_phone(self):
        try:
            status, data = request_json(self.backend_api_url("/phone/status"), headers=self.auth_headers())
            if status == 200 and data.get("online"):
                return "Online", "Online"
            if status == 200:
                return "Offline", "Offline"
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

    def scan_apps(self):
        self.configure_scan_buttons("disabled", "Skanuje...")
        self.log("Skanuje aplikacje")
        threading.Thread(target=self._scan_apps_worker, daemon=True).start()

    def _scan_apps_worker(self):
        try:
            existing_apps = load_existing_apps()
            discovered_apps = scan_installed_apps()
            merged_apps = merge_discovered_apps(existing_apps, discovered_apps)
            save_apps_json(merged_apps)
            found = len(discovered_apps)
            added = len(merged_apps) - len(existing_apps)
            self.after(0, lambda: self._scan_apps_finished(found, added))
        except Exception as error:
            self.after(0, lambda err=error: self._scan_apps_failed(err))

    def _scan_apps_finished(self, found, added):
        self.configure_scan_buttons("normal", "Skanuj aplikacje")
        self.log(f"Skan aplikacji gotowy: znaleziono {found}, dodano {added}")
        if self.active_tab == "aplikacje":
            self.apps_loaded = False
            self.reload_apps_view()

    def _scan_apps_failed(self, error):
        self.configure_scan_buttons("normal", "Skanuj aplikacje")
        self.log(f"Błąd skanowania aplikacji: {error}")

    def configure_scan_buttons(self, state, text):
        for button in getattr(self, "scan_app_buttons", []):
            button.configure(state=state, text=text)

    def clean_apps(self):
        if hasattr(self, "clean_apps_button"):
            self.clean_apps_button.configure(state="disabled", text="Czyszczę...")
        self.log("Czyszczenie listy aplikacji...")
        threading.Thread(target=self._clean_apps_worker, daemon=True).start()

    def _clean_apps_worker(self):
        try:
            result = clean_apps_json()
            self.after(0, lambda: self._clean_apps_finished(result))
        except Exception as error:
            self.after(0, lambda err=error: self._clean_apps_failed(err))

    def _clean_apps_finished(self, result):
        if hasattr(self, "clean_apps_button"):
            self.clean_apps_button.configure(state="normal", text="Wyczyść listę")
        self.log(f"Czyszczenie zakończone: usunięto {result['removed']}, zostało {result['after']}")
        if self.active_tab == "aplikacje":
            self.apps_loaded = False
            self.reload_apps_view()

    def _clean_apps_failed(self, error):
        if hasattr(self, "clean_apps_button"):
            self.clean_apps_button.configure(state="normal", text="Wyczyść listę")
        self.log(f"Błąd czyszczenia aplikacji: {error}")

    def autofill_manual_key(self):
        if not self.manual_key.get().strip() and self.manual_label.get().strip():
            self.manual_key.set(normalize_app_key(self.manual_label.get()))

    def choose_manual_app_file(self):
        file_path = filedialog.askopenfilename(
            title="Wybierz aplikację",
            filetypes=[
                ("Aplikacje i skróty", "*.exe *.lnk"),
                ("EXE", "*.exe"),
                ("Skróty", "*.lnk"),
                ("Wszystkie pliki", "*.*"),
            ],
        )
        if not file_path:
            return
        suffix = Path(file_path).suffix.lower()
        if suffix == ".lnk":
            self.manual_type.set("lnk")
        elif suffix == ".exe":
            self.manual_type.set("exe")
        self.manual_command.set(file_path)
        if not self.manual_label.get().strip():
            self.manual_label.set(Path(file_path).stem)
        self.autofill_manual_key()
        self.manual_selected_text.set(f"{self.manual_label.get()} • {short_path(file_path)}")

    def save_manual_app(self):
        label = self.manual_label.get().strip()
        key = normalize_app_key(self.manual_key.get() or label)
        app_type = self.manual_type.get().strip().lower()
        command = self.manual_command.get().strip()
        arguments = self.manual_arguments.get().strip()

        if not label or not key or not command:
            self.log("Uzupełnij label, klucz i ścieżkę/komendę.")
            return
        if app_type not in {"exe", "lnk", "uri", "command"}:
            self.log(f"Nieobsługiwany typ aplikacji: {app_type}")
            return

        try:
            apps = load_existing_apps()
            entry = {
                "label": label,
                "type": app_type,
                "discovered": False,
                "hidden": False,
                "manual": True,
                "key": key,
                "name": key,
            }
            if app_type == "command":
                entry["command"] = command
            elif app_type == "uri":
                entry["uri"] = command
                entry["launch_path"] = command
            else:
                entry["launch_path"] = command
                if app_type == "exe":
                    entry["path"] = command
                    entry["process"] = Path(command).name
            if arguments:
                entry["arguments"] = arguments

            apps[key] = entry
            save_apps_json(apps)
            self.log(f"Dodano aplikację: {label}")
            self.manual_label.set("")
            self.manual_key.set("")
            self.manual_command.set("")
            self.manual_arguments.set("")
            self.manual_selected_text.set("Nie wybrano pliku")
            self.apps_loaded = False
            if self.active_tab == "aplikacje":
                self.reload_apps_view()
        except Exception as error:
            self.log(f"Błąd zapisu aplikacji: {error}")

    def open_app_action(self, app_key):
        threading.Thread(target=self._open_app_worker, args=(app_key,), daemon=True).start()

    def _open_app_worker(self, app_key):
        try:
            result = open_app(app_key)
            message = f"Otwieram {app_key}" if result == "opened" else f"Nie znam aplikacji: {app_key}"
        except Exception as error:
            message = f"Błąd otwierania {app_key}: {error}"
        self.after(0, lambda: self.log(message))

    def close_app_action(self, app_key):
        threading.Thread(target=self._close_app_worker, args=(app_key,), daemon=True).start()

    def _close_app_worker(self, app_key):
        try:
            result = close_app(app_key)
            if result == "closed":
                message = f"Zamykam {app_key}"
            elif result == "not_running":
                message = f"{app_key} nie jest uruchomiona"
            else:
                message = f"Zamykanie nieobsługiwane: {app_key}"
        except Exception as error:
            message = f"Błąd zamykania {app_key}: {error}"
        self.after(0, lambda: self.log(message))


if __name__ == "__main__":
    app = JarvisControlCenter()
    app.mainloop()
