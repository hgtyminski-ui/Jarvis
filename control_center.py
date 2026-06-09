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

from actions import app_label_from_entry, close_app, load_apps_raw, load_notes, open_app
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


def request_json(url, headers=None, timeout=1.5):
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        return response.status, json.loads(body) if body else {}


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
        self.active_tab = "control"
        self.app_filter = tk.StringVar(value="Wszystkie")
        self.app_search = tk.StringVar(value="")
        self.manual_label = tk.StringVar(value="")
        self.manual_key = tk.StringVar(value="")
        self.manual_type = tk.StringVar(value="exe")
        self.manual_command = tk.StringVar(value="")
        self.manual_arguments = tk.StringVar(value="")
        self.apps_cache = []
        self.apps_loaded = False
        self.apps_loading = False
        self.apps_page = 0
        self.apps_per_page = 50
        self.scan_app_buttons = []

        self.build_ui()
        self.switch_tab("control")
        self.refresh_status()

    def build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.bg_canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.bg_canvas.bind("<Configure>", self.draw_grid)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=28, pady=(20, 12))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            header,
            text="JARVIS CONTROL CENTER",
            text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=18, weight="bold"),
        )
        title.grid(row=0, column=0, sticky="w")

        tabs = ctk.CTkFrame(header, fg_color="transparent")
        tabs.grid(row=1, column=0, sticky="w", pady=(12, 0))
        for index, tab in enumerate(["CHAT", "APLIKACJE", "NOTATKI", "USTAWIENIA", "CONTROL"]):
            key = tab.lower()
            button = self.make_button(tabs, tab, lambda name=key: self.switch_tab(name), width=120, height=30)
            button.grid(row=0, column=index, padx=(0, 8), sticky="w")
            self.tabs[key] = button

        shell = ctk.CTkFrame(self, fg_color="transparent")
        shell.grid(row=1, column=0, sticky="nsew", padx=28, pady=(0, 24))
        shell.grid_columnconfigure(0, minsize=260, weight=0)
        shell.grid_columnconfigure(1, weight=1)
        shell.grid_columnconfigure(2, minsize=300, weight=0)
        shell.grid_rowconfigure(0, weight=1)

        self.status_panel = self.make_panel(shell, "SYSTEM STATUS")
        self.status_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        self.build_status_panel()

        self.content = ctk.CTkFrame(shell, fg_color="transparent")
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
        self.content.grid_rowconfigure(0, weight=1)
        self.build_views()

        self.log_panel = self.make_panel(shell, "CONSOLE LOG")
        self.log_panel.grid(row=0, column=2, sticky="nsew", padx=(14, 0))
        self.log_panel.grid_rowconfigure(1, weight=1)
        self.log_panel.grid_columnconfigure(0, weight=1)
        self.build_log_panel()

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
        frame = ctk.CTkFrame(parent, fg_color=PANEL, border_color=LINE, border_width=1, corner_radius=8)
        frame.grid_columnconfigure(0, weight=1)
        label = ctk.CTkLabel(
            frame,
            text=title,
            text_color=CYAN,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
        )
        label.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 8))
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
            corner_radius=8,
            width=width,
            height=height,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
        )

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
        row_frame.grid(row=row, column=0, sticky="ew", padx=14, pady=5)
        row_frame.grid_columnconfigure(1, weight=1)

        dot = ctk.CTkLabel(row_frame, text="●", text_color=UNKNOWN, font=ctk.CTkFont(size=9, weight="bold"))
        dot.grid(row=0, column=0, padx=(0, 8), sticky="w")
        label = ctk.CTkLabel(
            row_frame,
            text=name.upper(),
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
        )
        label.grid(row=0, column=1, sticky="w")
        value_label = ctk.CTkLabel(
            row_frame,
            text=value,
            text_color=TEXT,
            anchor="e",
            font=ctk.CTkFont(family="Consolas", size=9),
        )
        value_label.grid(row=0, column=2, padx=(8, 0), sticky="e")

        self.status_dots[name] = dot
        self.status_labels[name] = value_label

    def build_log_panel(self):
        self.log_box = ctk.CTkTextbox(
            self.log_panel,
            fg_color="#07101d",
            text_color=TEXT,
            border_color="#123249",
            border_width=1,
            corner_radius=8,
            font=ctk.CTkFont(family="Consolas", size=10),
        )
        self.log_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.log_box.configure(state="disabled")

    def build_views(self):
        self.views["control"] = self.create_control_view()
        self.views["aplikacje"] = self.create_apps_view()
        self.views["ustawienia"] = self.create_settings_view()
        self.views["chat"] = self.create_chat_view()
        self.views["notatki"] = self.create_notes_view()

    def switch_tab(self, tab):
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
        grid.grid(row=1, column=0, sticky="n", padx=18, pady=18)
        for column in range(2):
            grid.grid_columnconfigure(column, minsize=240)

        actions = [
            ("Start Processor", self.start_processor, PURPLE),
            ("Start Backend", self.start_backend, CYAN),
            ("Start Agent", self.start_agent, BLUE),
            ("Połącz telefon", self.open_pairing, PURPLE),
            ("Skanuj aplikacje", self.scan_apps, PURPLE),
            ("Odśwież status", self.refresh_status, CYAN),
        ]
        for index, (label, command, color) in enumerate(actions):
            button = self.make_button(grid, label, command, border_color=color, width=230, height=46)
            button.grid(row=index // 2, column=index % 2, padx=10, pady=10, sticky="n")
            if label == "Skanuj aplikacje":
                self.scan_apps_button = button
                self.scan_app_buttons.append(button)
            if label == "Odśwież status":
                self.refresh_button = button

        hint = ctk.CTkLabel(
            frame,
            text="CONTROL HUB READY",
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
        )
        hint.grid(row=2, column=0, pady=(0, 16))
        return frame

    def create_apps_view(self):
        frame = self.make_panel(self.content, "APLIKACJE")
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(4, weight=1)

        tools = ctk.CTkFrame(frame, fg_color="transparent")
        tools.grid(row=1, column=0, sticky="ew", padx=14, pady=(4, 10))
        tools.grid_columnconfigure(0, weight=1)

        self.app_search_entry = ctk.CTkEntry(
            tools,
            textvariable=self.app_search,
            placeholder_text="Szukaj aplikacji...",
            fg_color=PANEL_2,
            text_color=TEXT,
            border_color=CYAN,
            border_width=1,
            corner_radius=8,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self.app_search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10))
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
            width=140,
        )
        self.filter_menu.grid(row=0, column=1, padx=(0, 10))

        scan_button = self.make_button(tools, "Skanuj aplikacje", self.scan_apps, border_color=PURPLE, width=150)
        scan_button.grid(row=0, column=2, sticky="e", padx=(0, 10))
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
        self.manual_form.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 10))

        self.apps_count_label = ctk.CTkLabel(
            frame,
            text="0 aplikacji",
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=10),
        )
        self.apps_count_label.grid(row=3, column=0, sticky="w", padx=14, pady=(0, 6))

        pager = ctk.CTkFrame(frame, fg_color="transparent")
        pager.grid(row=5, column=0, sticky="ew", padx=14, pady=(0, 14))
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
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
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
            corner_radius=8,
        )
        self.apps_grid.grid(row=4, column=0, sticky="nsew", padx=14, pady=(0, 14))
        return frame

    def create_manual_app_form(self, parent):
        form = ctk.CTkFrame(parent, fg_color=PANEL_2, border_color=LINE, border_width=1, corner_radius=8)
        for column in range(6):
            form.grid_columnconfigure(column, weight=1 if column in {0, 1, 3} else 0)

        ctk.CTkLabel(
            form,
            text="DODAJ APLIKACJĘ RĘCZNIE",
            text_color=CYAN,
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
        ).grid(row=0, column=0, columnspan=6, sticky="w", padx=12, pady=(10, 6))

        label_entry = self.make_entry(form, self.manual_label, "Label / nazwa")
        label_entry.grid(row=1, column=0, sticky="ew", padx=(12, 8), pady=6)
        label_entry.bind("<FocusOut>", lambda _event: self.autofill_manual_key())

        self.make_entry(form, self.manual_key, "Klucz aplikacji").grid(
            row=1, column=1, sticky="ew", padx=(0, 8), pady=6
        )

        ctk.CTkOptionMenu(
            form,
            values=["exe", "lnk", "uri", "command"],
            variable=self.manual_type,
            fg_color=PANEL,
            button_color=BLUE,
            button_hover_color=PURPLE,
            dropdown_fg_color=PANEL,
            text_color=TEXT,
            width=110,
        ).grid(row=1, column=2, sticky="ew", padx=(0, 8), pady=6)

        self.make_entry(form, self.manual_command, "Ścieżka albo komenda").grid(
            row=1, column=3, sticky="ew", padx=(0, 8), pady=6
        )
        self.make_entry(form, self.manual_arguments, "Argumenty").grid(
            row=1, column=4, sticky="ew", padx=(0, 8), pady=6
        )

        self.make_button(form, "Wybierz plik", self.choose_manual_app_file, border_color=BLUE, width=118, height=30).grid(
            row=1, column=5, sticky="ew", padx=(0, 12), pady=6
        )
        self.make_button(form, "Zapisz", self.save_manual_app, border_color=PURPLE, width=118, height=30).grid(
            row=2, column=5, sticky="ew", padx=(0, 12), pady=(0, 10)
        )
        return form

    def make_entry(self, parent, variable, placeholder):
        return ctk.CTkEntry(
            parent,
            textvariable=variable,
            placeholder_text=placeholder,
            fg_color=PANEL,
            text_color=TEXT,
            border_color=CYAN,
            border_width=1,
            corner_radius=8,
            font=ctk.CTkFont(family="Consolas", size=10),
        )

    def create_settings_view(self):
        frame = self.make_panel(self.content, "USTAWIENIA")
        self.settings_grid = ctk.CTkFrame(frame, fg_color="transparent")
        self.settings_grid.grid(row=1, column=0, sticky="nsew", padx=16, pady=16)
        self.settings_grid.grid_columnconfigure(1, weight=1)
        return frame

    def create_chat_view(self):
        frame = self.make_panel(self.content, "CHAT")
        frame.grid_rowconfigure(1, weight=1)
        placeholder = ctk.CTkLabel(
            frame,
            text="CHAT PANEL\nProsty podgląd Control Center. Rozmowa zostaje w Jarvis Remote / Desktop GUI.",
            text_color=MUTED,
            justify="center",
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
        )
        placeholder.grid(row=1, column=0, sticky="nsew", padx=24, pady=24)
        return frame

    def create_notes_view(self):
        frame = self.make_panel(self.content, "NOTATKI")
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        self.notes_list = ctk.CTkScrollableFrame(
            frame,
            fg_color="#07101d",
            border_color="#123249",
            border_width=1,
            corner_radius=8,
        )
        self.notes_list.grid(row=1, column=0, sticky="nsew", padx=14, pady=(6, 14))
        return frame

    def refresh_settings_view(self):
        for widget in self.settings_grid.winfo_children():
            widget.destroy()

        config = load_config()
        settings = [
            ("backend_url", config.get("backend_url") or "http://127.0.0.1:8000"),
            ("processor_url", config.get("processor_url") or "http://127.0.0.1:8001"),
            ("device_id", config.get("device_id") or "local-pc"),
            ("api_token", "••••••••" if config.get("api_token") else "brak"),
            ("base_url LM Studio", config.get("base_url") or ""),
            ("model", config.get("model") or "local-model"),
        ]
        for row, (label, value) in enumerate(settings):
            ctk.CTkLabel(
                self.settings_grid,
                text=label.upper(),
                text_color=MUTED,
                font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            ).grid(row=row, column=0, sticky="w", padx=(0, 16), pady=8)
            ctk.CTkLabel(
                self.settings_grid,
                text=str(value),
                text_color=TEXT,
                anchor="w",
                font=ctk.CTkFont(family="Consolas", size=11),
            ).grid(row=row, column=1, sticky="ew", pady=8)

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
                row=0, column=0, padx=14, pady=14, sticky="w"
            )
            return

        for row, note in enumerate(notes):
            text = f"{note.get('title') or 'Bez tytułu'}\n{note.get('created_at') or 'brak daty'}"
            ctk.CTkLabel(
                self.notes_list,
                text=text,
                text_color=TEXT,
                justify="left",
                anchor="w",
                font=ctk.CTkFont(family="Consolas", size=11),
            ).grid(row=row, column=0, sticky="ew", padx=14, pady=8)

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
                row=0, column=0, padx=14, pady=14, sticky="w"
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
        card = ctk.CTkFrame(self.apps_grid, fg_color=PANEL, border_color=LINE, border_width=1, corner_radius=8)
        card.grid(row=row, column=column, padx=8, pady=8, sticky="nsew")
        card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            card,
            text=str(label),
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            card,
            text=f"type: {record['type']}",
            text_color=CYAN if record["discovered"] else PURPLE,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
        ).grid(row=1, column=0, columnspan=2, sticky="ew", padx=12)
        ctk.CTkLabel(
            card,
            text=short_path(record["path"]),
            text_color=MUTED,
            anchor="w",
            wraplength=210,
            font=ctk.CTkFont(family="Consolas", size=9),
        ).grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(4, 10))

        self.make_button(card, "Otwórz", lambda target=key: self.open_app_action(target), border_color=CYAN, width=96, height=30).grid(
            row=3, column=0, sticky="w", padx=(12, 4), pady=(0, 12)
        )
        self.make_button(card, "Zamknij", lambda target=key: self.close_app_action(target), border_color=DANGER, width=96, height=30).grid(
            row=3, column=1, sticky="e", padx=(4, 12), pady=(0, 12)
        )

    def log(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("1.0", f"[{timestamp}] {message}\n")
        lines = self.log_box.get("1.0", "end-1c").splitlines()
        if len(lines) > 120:
            self.log_box.delete("121.0", "end")
        self.log_box.configure(state="disabled")

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
        self.log("Status odświeżony")
        if hasattr(self, "refresh_button"):
            self.refresh_button.configure(state="normal", text="Odśwież status")

    def auth_headers(self):
        token = load_config().get("api_token") or ""
        return {"X-Jarvis-Token": token} if token else {}

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
        try:
            status, data = request_json(BACKEND_AGENTS_URL, headers=self.auth_headers())
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
            status, data = request_json(PHONE_STATUS_URL, headers=self.auth_headers())
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
