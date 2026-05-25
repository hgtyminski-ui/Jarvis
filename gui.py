import contextlib
import datetime
import io
import json
import math
import sys
import threading
import tkinter as tk

import customtkinter as ctk

try:
    import requests
except ImportError:
    requests = None

from actions import (
    close_app,
    create_note,
    delete_note,
    is_app_running,
    load_app_categories,
    load_apps,
    load_notes,
    load_processes,
    open_app,
    parse_ai_json,
    parse_local_action,
)
from ai_client import create_client
from config import CONFIG_PATH, ConfigError, load_config
from memory import add_assistant_message, add_user_message, create_messages
from text_utils import normalize_text

try:
    import psutil
except ImportError:
    psutil = None


BG = "#05070d"
PANEL = "#0b1220"
PANEL_2 = "#0f1b2d"
CYAN = "#00eaff"
BLUE = "#2f7dff"
PURPLE = "#8a5cff"
GREEN = "#20e080"
GREEN_HOVER = "#27f090"
RED = "#ff3b5c"
RED_HOVER = "#ff5470"
TEXT = "#d7f7ff"
MUTED = "#7aa5b3"
LINE = "#1b4f6b"
CATEGORY_STYLES = [
    (PANEL_2, CYAN),
    (PANEL_2, BLUE),
    (PANEL_2, PURPLE),
    (PANEL_2, GREEN),
    (PANEL, BLUE),
    (PANEL, PURPLE),
]
PHONE_APP_TARGETS = [
    "spotify",
    "youtube",
    "netflix",
    "discord",
    "steam",
    "whatsapp",
    "teams",
]


class JarvisGUI(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        super().__init__()

        self.title("Jarvis")
        self.geometry("1200x750")
        self.minsize(980, 620)
        self.configure(fg_color=BG)

        self.assistant_name = "Jarvis"
        self.client = None
        self.config = None
        self.messages = None
        self.is_busy = False
        self.is_recording = False
        self.is_fullscreen = False
        self.apps_panel_visible = False
        self.pulse_phase = 0
        self.wave_phase = 0
        self.visual_mode = "core"
        self.visual_transition_progress = 0.0
        self.wave_return_start_progress = 1.0
        self.system_labels = {}
        self.app_action_buttons = {}
        self.lm_server_label = None
        self.lm_model_label = None
        self.phone_status_label = None
        self.phone_seen_label = None
        self.phone_command_label = None
        self.phone_status_refreshing = False
        self.settings_window = None
        self.notes_window = None
        self.notes_list_frame = None
        self.note_window = None
        self.note_preview_window = None
        self.pending_note_content = None
        self.control_mode = "pc"

        self.bind("<F11>", self.toggle_fullscreen)
        self.bind("<Escape>", self.exit_fullscreen)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.build_header()
        self.build_dashboard()
        self.build_input_bar()
        self.load_jarvis()
        self.update_clock_and_metrics()
        self.animate_core()

    def build_header(self):
        header = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        header.grid(row=0, column=0, padx=22, pady=(16, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)
        header.grid_columnconfigure(2, weight=0)

        self.title_label = ctk.CTkLabel(
            header,
            text="JARVIS",
            text_color=CYAN,
            font=ctk.CTkFont(family="Segoe UI", size=46, weight="bold"),
        )
        self.title_label.grid(row=0, column=0, sticky="ew")

        self.status_label = ctk.CTkLabel(
            header,
            text="Gotowy",
            text_color=MUTED,
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.status_label.grid(row=1, column=0, columnspan=3, sticky="ew")

        self.control_mode_selector = ctk.CTkSegmentedButton(
            header,
            values=["Steruj PC", "Steruj telefonem"],
            command=self.set_control_mode,
            height=30,
            selected_color=CYAN,
            selected_hover_color=BLUE,
            unselected_color=PANEL_2,
            unselected_hover_color=PANEL,
            text_color=TEXT,
            font=ctk.CTkFont(size=12, weight="bold"),
            corner_radius=6,
        )
        self.control_mode_selector.set("Steruj PC")
        self.control_mode_selector.grid(row=0, column=1, padx=(12, 0), pady=(4, 0), sticky="e")

        self.close_button = ctk.CTkButton(
            header,
            text="X",
            command=self.close_window,
            width=34,
            height=28,
            fg_color="#0b1220",
            hover_color="#2f7dff",
            text_color="#ff3b5c",
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.close_button.grid(row=0, column=2, padx=(10, 0), pady=(4, 0), sticky="ne")

        ctk.CTkFrame(header, fg_color=CYAN, height=1, corner_radius=0).grid(
            row=2,
            column=0,
            columnspan=3,
            padx=130,
            pady=(8, 0),
            sticky="ew",
        )

    def build_dashboard(self):
        dashboard = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        dashboard.grid(row=1, column=0, padx=22, pady=(0, 12), sticky="nsew")
        dashboard.grid_columnconfigure(0, weight=0, minsize=195)
        dashboard.grid_columnconfigure(1, weight=0, minsize=1)
        dashboard.grid_columnconfigure(2, weight=1)
        dashboard.grid_columnconfigure(3, weight=0, minsize=1)
        dashboard.grid_columnconfigure(4, weight=0, minsize=230)
        dashboard.grid_rowconfigure(0, weight=1)

        self.left_panel = self.create_panel(dashboard)
        self.left_panel.grid(row=0, column=0, padx=(0, 10), sticky="nsew")
        self.build_app_launcher(self.left_panel)

        ctk.CTkFrame(dashboard, fg_color=CYAN, width=1, corner_radius=0).grid(
            row=0,
            column=1,
            sticky="ns",
        )

        self.center_panel = self.create_panel(dashboard)
        self.center_panel.grid(row=0, column=2, padx=10, sticky="nsew")
        self.center_panel.grid_columnconfigure(0, weight=1)
        self.center_panel.grid_rowconfigure(1, weight=1)
        self.build_center(self.center_panel)

        ctk.CTkFrame(dashboard, fg_color=CYAN, width=1, corner_radius=0).grid(
            row=0,
            column=3,
            sticky="ns",
        )

        self.right_panel = self.create_panel(dashboard)
        self.right_panel.grid(row=0, column=4, padx=(10, 0), sticky="nsew")
        self.build_system_status(self.right_panel)
        self.build_apps_panel(dashboard)

    def build_input_bar(self):
        self.input_frame = ctk.CTkFrame(
            self,
            fg_color=PANEL,
            border_width=1,
            border_color=BLUE,
            corner_radius=8,
        )
        self.input_frame.grid(row=2, column=0, padx=18, pady=(0, 16), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkTextbox(
            self.input_frame,
            height=86,
            wrap="word",
            font=ctk.CTkFont(size=14),
            text_color=TEXT,
            fg_color="#05070d",
            border_width=1,
            border_color="#1b4f6b",
            corner_radius=8,
        )
        self.entry.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=10, sticky="ew")
        self.entry.bind("<Return>", self.on_entry_return)
        self.entry.bind("<Shift-Return>", self.on_entry_shift_return)

        self.send_button = self.create_action_button(
            self.input_frame,
            "Wyślij",
            self.send_text,
            fg_color=PANEL_2,
            hover_color=BLUE,
        )
        self.send_button.grid(row=0, column=1, padx=(0, 8), pady=(10, 6), sticky="ew")

        self.listen_button = self.create_action_button(self.input_frame, "Listen", None)
        self.listen_button.grid(row=0, column=2, padx=(0, 10), pady=(10, 6), sticky="ew")
        self.listen_button.bind("<ButtonPress-1>", self.on_listen_press)
        self.listen_button.bind("<ButtonRelease-1>", self.on_listen_release)

        self.clear_button = self.create_action_button(
            self.input_frame,
            "Wyczyść",
            self.clear_history,
            fg_color="#0f1b2d",
            hover_color="#2f7dff",
        )
        self.clear_button.grid(row=1, column=1, columnspan=2, padx=(0, 10), pady=(0, 10), sticky="ew")

    def create_panel(self, parent):
        return ctk.CTkFrame(
            parent,
            fg_color=PANEL,
            border_width=1,
            border_color="#1b4f6b",
            corner_radius=8,
        )

    def create_action_button(self, parent, text, command, fg_color=PANEL, hover_color=BLUE):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=112,
            height=36,
            fg_color=fg_color,
            hover_color=hover_color,
            text_color=TEXT,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
        )

    def build_app_launcher(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(9, weight=1)

        self.apps_toggle_button = self.create_action_button(
            parent,
            "Aplikacje",
            self.toggle_apps_panel,
            fg_color="#0b1220",
            hover_color="#2f7dff",
        )
        self.apps_toggle_button.grid(row=0, column=0, padx=14, pady=(16, 5), sticky="ew")

        self.settings_button = self.create_action_button(
            parent,
            "Ustawienia",
            self.open_settings_window,
            fg_color="#0b1220",
            hover_color=BLUE,
        )
        self.settings_button.grid(row=1, column=0, padx=14, pady=5, sticky="ew")

        self.notes_toggle_button = self.create_action_button(
            parent,
            "Notatki",
            self.toggle_notes_panel,
            fg_color="#0b1220",
            hover_color=BLUE,
        )
        self.notes_toggle_button.grid(row=2, column=0, padx=14, pady=5, sticky="ew")

        ctk.CTkLabel(
            parent,
            text="LOCAL COMMAND GRID",
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
        ).grid(row=10, column=0, padx=14, pady=(18, 0), sticky="s")

    def toggle_notes_panel(self):
        self.open_notes_window()

    def open_notes_window(self):
        if self.notes_window and self.notes_window.winfo_exists():
            self.notes_window.focus()
            self.refresh_notes_list()
            return

        window = ctk.CTkToplevel(self)
        window.title("Notatki")
        window.geometry("620x560")
        window.minsize(520, 420)
        window.configure(fg_color=BG)
        window.transient(self)
        window.grab_set()
        self.notes_window = window

        def close_window():
            self.notes_window = None
            self.notes_list_frame = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close_window)

        frame = ctk.CTkFrame(
            window,
            fg_color=PANEL,
            border_width=1,
            border_color=CYAN,
            corner_radius=8,
        )
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            frame,
            text="NOTATKI",
            text_color=CYAN,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=(14, 10), sticky="ew")

        button_row = ctk.CTkFrame(frame, fg_color="transparent")
        button_row.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
        for column in range(3):
            button_row.grid_columnconfigure(column, weight=1)

        new_button = ctk.CTkButton(
            button_row,
            text="Nowa notatka",
            command=self.open_new_note_window,
            height=32,
            fg_color=PANEL,
            hover_color=BLUE,
            text_color=GREEN,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        new_button.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        refresh_button = ctk.CTkButton(
            button_row,
            text="Odśwież notatki",
            command=self.refresh_notes_list,
            height=32,
            fg_color="#0b1220",
            hover_color="#2f7dff",
            text_color=TEXT,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        refresh_button.grid(row=0, column=1, padx=6, sticky="ew")

        close_button = ctk.CTkButton(
            button_row,
            text="Zamknij",
            command=close_window,
            height=32,
            fg_color="#0f1b2d",
            hover_color="#2f7dff",
            text_color=TEXT,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        close_button.grid(row=0, column=2, padx=(6, 0), sticky="ew")

        self.notes_list_frame = ctk.CTkScrollableFrame(
            frame,
            fg_color="#05070d",
            border_width=1,
            border_color=LINE,
            corner_radius=8,
            scrollbar_button_color="#2f7dff",
            scrollbar_button_hover_color=CYAN,
        )
        self.notes_list_frame.grid(row=2, column=0, padx=14, pady=(0, 14), sticky="nsew")
        self.notes_list_frame.grid_columnconfigure(0, weight=1)
        self.refresh_notes_list()

    def refresh_notes_list(self):
        if not self.notes_list_frame:
            return

        for widget in self.notes_list_frame.winfo_children():
            widget.destroy()

        try:
            notes = load_notes()
        except Exception as e:
            self.set_error_status(e)
            self.after(1500, lambda: self.set_status("Gotowy"))
            ctk.CTkLabel(
                self.notes_list_frame,
                text="Błąd ładowania notatek",
                text_color="#ff3b5c",
                font=ctk.CTkFont(size=12, weight="bold"),
            ).grid(row=0, column=0, padx=12, pady=12, sticky="ew")
            return

        if not notes:
            ctk.CTkLabel(
                self.notes_list_frame,
                text="Brak notatek",
                text_color=MUTED,
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=0, padx=12, pady=12, sticky="ew")
            return

        for index, note in enumerate(notes):
            self.add_note_row(self.notes_list_frame, index, note)

    def add_note_row(self, parent, row, note):
        title = str(note.get("title") or "Bez tytułu")
        created_at = self.format_note_timestamp(note.get("created_at", ""))
        note_path = note.get("path", "")

        note_frame = ctk.CTkFrame(
            parent,
            fg_color="#0f1b2d",
            border_width=1,
            border_color="#1b4f6b",
            corner_radius=6,
        )
        note_frame.grid(row=row, column=0, padx=8, pady=4, sticky="ew")
        note_frame.grid_columnconfigure(0, weight=1)
        note_frame.grid_columnconfigure(1, weight=0)

        title_button = ctk.CTkButton(
            note_frame,
            text=title,
            command=lambda selected_note=note: self.open_note_preview(selected_note),
            anchor="w",
            height=30,
            fg_color="#0f1b2d",
            hover_color="#2f7dff",
            text_color=TEXT,
            border_width=0,
            corner_radius=4,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        title_button.grid(row=0, column=0, padx=(8, 6), pady=(7, 0), sticky="ew")

        ctk.CTkLabel(
            note_frame,
            text=created_at,
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(size=10),
        ).grid(row=1, column=0, padx=12, pady=(0, 7), sticky="ew")

        delete_button = ctk.CTkButton(
            note_frame,
            text="Usuń",
            command=lambda path=note_path: self.delete_note_from_gui(path),
            width=70,
            height=28,
            fg_color=PANEL,
            hover_color=BLUE,
            text_color=RED,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        delete_button.grid(row=0, column=1, rowspan=2, padx=(0, 8), pady=8, sticky="e")

    def format_note_timestamp(self, value):
        if not value:
            return "brak daty"

        try:
            return datetime.datetime.fromisoformat(str(value)).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return str(value)[:16]

    def open_note_preview(self, note):
        if self.note_preview_window and self.note_preview_window.winfo_exists():
            self.note_preview_window.destroy()

        title = str(note.get("title") or "Bez tytułu")
        content = str(note.get("content") or "")
        created_at = self.format_note_timestamp(note.get("created_at", ""))
        note_path = note.get("path", "")

        window = ctk.CTkToplevel(self.notes_window or self)
        window.title("Podgląd notatki")
        window.geometry("620x500")
        window.minsize(520, 420)
        window.configure(fg_color=BG)
        window.transient(self.notes_window or self)
        window.grab_set()
        self.note_preview_window = window

        def close_window():
            self.note_preview_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close_window)

        frame = ctk.CTkFrame(
            window,
            fg_color=PANEL,
            border_width=1,
            border_color=CYAN,
            corner_radius=8,
        )
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            frame,
            text=title,
            text_color=CYAN,
            wraplength=540,
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=(14, 10), sticky="ew")

        content_box = ctk.CTkTextbox(
            frame,
            wrap="word",
            font=ctk.CTkFont(size=13),
            text_color=TEXT,
            fg_color="#05070d",
            border_width=1,
            border_color="#1b4f6b",
            corner_radius=6,
        )
        content_box.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="nsew")
        content_box.insert("1.0", content or "Brak treści")
        content_box.configure(state="disabled")

        ctk.CTkLabel(
            frame,
            text=created_at,
            text_color=MUTED,
            font=ctk.CTkFont(size=12),
        ).grid(row=2, column=0, padx=14, pady=(0, 10), sticky="ew")

        button_row = ctk.CTkFrame(frame, fg_color="transparent")
        button_row.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="ew")
        for column in range(2):
            button_row.grid_columnconfigure(column, weight=1)

        delete_button = ctk.CTkButton(
            button_row,
            text="Usuń",
            command=lambda path=note_path, top=window: self.delete_note_from_gui(path, top),
            height=34,
            fg_color=PANEL,
            hover_color=BLUE,
            text_color=RED,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        delete_button.grid(row=0, column=0, padx=(0, 6), sticky="ew")

        close_button = ctk.CTkButton(
            button_row,
            text="Zamknij",
            command=close_window,
            height=34,
            fg_color="#0f1b2d",
            hover_color="#2f7dff",
            text_color=TEXT,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        close_button.grid(row=0, column=1, padx=(6, 0), sticky="ew")

    def delete_note_from_gui(self, note_path, window_to_close=None):
        self.set_status("Wykonuję")
        result = delete_note(note_path)

        if result in ["deleted", "missing"]:
            if window_to_close and window_to_close.winfo_exists():
                window_to_close.destroy()
                if window_to_close == self.note_preview_window:
                    self.note_preview_window = None
            self.refresh_notes_list()
            self.set_status("Gotowy")
            return

        self.set_error_status("nie udało się usunąć notatki")
        self.after(1500, lambda: self.set_status("Gotowy"))

    def open_new_note_window(self):
        if self.note_window and self.note_window.winfo_exists():
            self.note_window.focus()
            return

        window = ctk.CTkToplevel(self.notes_window or self)
        window.title("Nowa notatka")
        window.geometry("460x430")
        window.resizable(False, False)
        window.configure(fg_color=BG)
        window.transient(self.notes_window or self)
        window.grab_set()
        self.note_window = window

        def close_window():
            self.note_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close_window)

        frame = ctk.CTkFrame(
            window,
            fg_color=PANEL,
            border_width=1,
            border_color=CYAN,
            corner_radius=8,
        )
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="NOWA NOTATKA",
            text_color=CYAN,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=(14, 10), sticky="ew")

        ctk.CTkLabel(
            frame,
            text="Tytuł",
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=1, column=0, padx=14, pady=(4, 3), sticky="ew")

        title_entry = ctk.CTkEntry(
            frame,
            fg_color="#05070d",
            text_color=TEXT,
            border_color="#1b4f6b",
            border_width=1,
            corner_radius=6,
        )
        title_entry.grid(row=2, column=0, padx=14, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(
            frame,
            text="Treść",
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=3, column=0, padx=14, pady=(4, 3), sticky="ew")

        content_box = ctk.CTkTextbox(
            frame,
            height=150,
            wrap="word",
            font=ctk.CTkFont(size=13),
            text_color=TEXT,
            fg_color="#05070d",
            border_width=1,
            border_color="#1b4f6b",
            corner_radius=6,
        )
        content_box.grid(row=4, column=0, padx=14, pady=(0, 8), sticky="ew")

        message_label = ctk.CTkLabel(
            frame,
            text="",
            text_color=GREEN_HOVER,
            wraplength=390,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        message_label.grid(row=5, column=0, padx=14, pady=(0, 6), sticky="ew")

        save_button = ctk.CTkButton(
            frame,
            text="Zapisz",
            command=lambda: self.save_note_from_window(title_entry, content_box, message_label),
            height=34,
            fg_color=PANEL,
            hover_color=BLUE,
            text_color=GREEN,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        save_button.grid(row=6, column=0, padx=14, pady=(0, 14), sticky="ew")
        title_entry.focus_set()

    def save_note_from_window(self, title_entry, content_box, message_label):
        title = title_entry.get().strip()
        content = content_box.get("1.0", "end-1c").strip()

        self.set_status("Wykonuję")
        try:
            result = create_note(content, title)
        except Exception as e:
            message_label.configure(text=f"Błąd zapisu: {e}", text_color="#ff3b5c")
            self.set_error_status(e)
            self.after(1500, lambda: self.set_status("Gotowy"))
            return

        if result != "saved":
            message_label.configure(text="Brakuje treści notatki.", text_color="#ff3b5c")
            self.set_error_status("brakuje treści notatki")
            self.after(1500, lambda: self.set_status("Gotowy"))
            return

        message_label.configure(text="Notatka zapisana.", text_color=GREEN_HOVER)
        self.append_history(f"{self.assistant_name}: Notatka zapisana.")
        content_box.delete("1.0", "end")
        title_entry.delete(0, "end")
        self.refresh_notes_list()
        self.set_status("Gotowy")

    def open_settings_window(self):
        if self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.focus()
            return

        config_data, error = self.read_settings_config()
        values = config_data or {}

        window = ctk.CTkToplevel(self)
        window.title("Ustawienia")
        window.geometry("420x520")
        window.resizable(False, False)
        window.configure(fg_color=BG)
        window.transient(self)
        window.grab_set()
        self.settings_window = window

        frame = ctk.CTkFrame(
            window,
            fg_color=PANEL,
            border_width=1,
            border_color=CYAN,
            corner_radius=8,
        )
        frame.pack(fill="both", expand=True, padx=16, pady=16)
        frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            frame,
            text="USTAWIENIA",
            text_color=CYAN,
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, padx=12, pady=(14, 10), sticky="ew")

        settings_vars = {
            "voice_enabled": tk.BooleanVar(value=bool(values.get("voice_enabled", True))),
            "whisper_model": tk.StringVar(value=str(values.get("whisper_model", "base"))),
            "sample_rate": tk.StringVar(value=str(values.get("sample_rate", 48000))),
            "temperature": tk.StringVar(value=str(values.get("temperature", 0.3))),
            "edge_voice": tk.StringVar(value=str(values.get("edge_voice", "pl-PL-MarekNeural"))),
            "edge_rate": tk.StringVar(value=str(values.get("edge_rate", "+0%"))),
            "animation_speed": tk.StringVar(value=str(values.get("animation_speed", 1.6))),
        }

        voice_checkbox = ctk.CTkCheckBox(
            frame,
            text="voice_enabled",
            variable=settings_vars["voice_enabled"],
            text_color=TEXT,
            fg_color=CYAN,
            hover_color="#2f7dff",
            border_color=CYAN,
        )
        voice_checkbox.grid(row=1, column=0, columnspan=2, padx=14, pady=8, sticky="w")

        row = 2
        for key, label in [
            ("whisper_model", "whisper_model"),
            ("sample_rate", "sample_rate"),
            ("temperature", "temperature"),
            ("edge_voice", "edge_voice"),
            ("edge_rate", "edge_rate"),
            ("animation_speed", "animation_speed"),
        ]:
            self.add_settings_entry(frame, row, label, settings_vars[key])
            row += 1

        message_label = ctk.CTkLabel(
            frame,
            text=f"Błąd config.json: {error}" if error else "",
            text_color="#ff3b5c" if error else GREEN_HOVER,
            wraplength=350,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        message_label.grid(row=row, column=0, columnspan=2, padx=14, pady=(8, 4), sticky="ew")

        save_button = ctk.CTkButton(
            frame,
            text="Zapisz",
            command=lambda: self.save_settings(config_data, settings_vars, message_label),
            height=34,
            fg_color=PANEL,
            hover_color=BLUE,
            text_color=GREEN,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        save_button.grid(row=row + 1, column=0, padx=(14, 6), pady=(8, 14), sticky="ew")
        if config_data is None:
            save_button.configure(state="disabled")

        close_button = ctk.CTkButton(
            frame,
            text="Zamknij",
            command=window.destroy,
            height=34,
            fg_color="#0f1b2d",
            hover_color="#2f7dff",
            text_color=TEXT,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        close_button.grid(row=row + 1, column=1, padx=(6, 14), pady=(8, 14), sticky="ew")

    def add_settings_entry(self, parent, row, label, variable):
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=row, column=0, padx=(14, 8), pady=7, sticky="ew")

        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            fg_color="#05070d",
            text_color=TEXT,
            border_color="#1b4f6b",
            border_width=1,
            corner_radius=6,
        )
        entry.grid(row=row, column=1, padx=(0, 14), pady=7, sticky="ew")

    def read_settings_config(self):
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as config_file:
                config_data = json.load(config_file)
        except json.JSONDecodeError as e:
            return None, str(e)
        except OSError as e:
            return None, str(e)

        if not isinstance(config_data, dict):
            return None, "config.json musi zawierać obiekt JSON"

        return config_data, None

    def save_settings(self, config_data, settings_vars, message_label):
        if config_data is None:
            message_label.configure(text="Nie można zapisać: config.json ma błąd.", text_color="#ff3b5c")
            self.set_error_status("config.json ma błąd")
            return

        try:
            updated_config = dict(config_data)
            updated_config["voice_enabled"] = bool(settings_vars["voice_enabled"].get())
            updated_config["whisper_model"] = settings_vars["whisper_model"].get().strip() or "base"
            updated_config["sample_rate"] = int(settings_vars["sample_rate"].get().strip())
            updated_config["temperature"] = float(settings_vars["temperature"].get().strip())
            updated_config["edge_voice"] = settings_vars["edge_voice"].get().strip() or "pl-PL-MarekNeural"
            updated_config["edge_rate"] = settings_vars["edge_rate"].get().strip() or "+0%"
            updated_config["animation_speed"] = self.clamp_animation_speed(
                float(settings_vars["animation_speed"].get().strip())
            )
        except ValueError as e:
            message_label.configure(text=f"Błąd wartości: {e}", text_color="#ff3b5c")
            self.set_error_status(e)
            return

        try:
            with CONFIG_PATH.open("w", encoding="utf-8") as config_file:
                json.dump(updated_config, config_file, ensure_ascii=False, indent=2)
                config_file.write("\n")

            self.config = load_config()
            self.update_system_status("Gotowy")
            self.refresh_lm_studio_status()
            message_label.configure(text="Zapisano ustawienia", text_color=GREEN_HOVER)
            self.append_history("Zapisano ustawienia")
            self.set_status("Gotowy")
        except Exception as e:
            message_label.configure(text=f"Błąd zapisu: {e}", text_color="#ff3b5c")
            self.set_error_status(e)

    def build_apps_panel(self, parent):
        self.apps_panel = ctk.CTkFrame(
            parent,
            fg_color=PANEL,
            border_width=1,
            border_color=CYAN,
            corner_radius=8,
        )
        self.apps_panel.grid(row=0, column=0, columnspan=5, padx=0, pady=0, sticky="nsew")
        self.apps_panel.grid_columnconfigure(0, weight=1)
        self.apps_panel.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self.apps_panel, fg_color="#0f1b2d", corner_radius=8)
        header.grid(row=0, column=0, padx=14, pady=(14, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="APLIKACJE",
            text_color=CYAN,
            anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, padx=12, pady=10, sticky="ew")

        self.apps_close_button = ctk.CTkButton(
            header,
            text="X",
            command=self.toggle_apps_panel,
            width=34,
            height=28,
            fg_color="#0b1220",
            hover_color="#2f7dff",
            text_color="#ff3b5c",
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.apps_refresh_button = ctk.CTkButton(
            header,
            text="Odśwież aplikacje",
            command=self.refresh_apps_list,
            width=150,
            height=28,
            fg_color="#0b1220",
            hover_color="#2f7dff",
            text_color=TEXT,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        self.apps_refresh_button.grid(row=0, column=1, padx=(8, 8), pady=8, sticky="e")
        self.apps_close_button.grid(row=0, column=2, padx=(0, 12), pady=8, sticky="e")

        self.apps_container = ctk.CTkScrollableFrame(
            self.apps_panel,
            fg_color="#05070d",
            border_width=1,
            border_color=LINE,
            corner_radius=8,
            scrollbar_button_color="#2f7dff",
            scrollbar_button_hover_color=CYAN,
        )
        self.apps_container.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")

        self.apps_panel.grid_remove()

    def toggle_apps_panel(self):
        self.apps_panel_visible = not self.apps_panel_visible

        if self.apps_panel_visible:
            self.apps_panel.grid()
            self.apps_panel.tkraise()
            self.refresh_apps_list()
        else:
            self.apps_panel.grid_remove()

    def get_app_categories(self, apps):
        categories = load_app_categories()
        if not categories:
            return {"Aplikacje": sorted(apps.keys())}

        seen = set()
        ordered_categories = {}

        for category, app_names in categories.items():
            valid_names = []
            for app_name in app_names:
                if app_name in apps and app_name not in seen:
                    valid_names.append(app_name)
                    seen.add(app_name)

            if valid_names:
                ordered_categories[category] = valid_names

        uncategorized = [app_name for app_name in sorted(apps.keys()) if app_name not in seen]
        if uncategorized:
            ordered_categories["Inne"] = uncategorized

        return ordered_categories

    def refresh_apps_list(self):
        if not hasattr(self, "apps_container"):
            return

        try:
            for widget in self.apps_container.winfo_children():
                widget.destroy()

            self.app_action_buttons = {}
            apps = load_apps()
            if self.is_phone_control_mode():
                apps = dict(apps)
                for phone_target in PHONE_APP_TARGETS:
                    apps.setdefault(phone_target, "")
            processes = load_processes()
            categories = self.get_app_categories(apps)
        except Exception as e:
            self.set_error_status(e)
            self.after(1500, lambda: self.set_status("Gotowy"))
            return

        if not apps:
            ctk.CTkLabel(
                self.apps_container,
                text="Brak aplikacji",
                text_color=MUTED,
                font=ctk.CTkFont(size=12),
            ).grid(row=0, column=0, padx=10, pady=10, sticky="ew")
            return

        category_count = len(categories)
        column_count = min(3, max(1, category_count))
        for column in range(column_count):
            self.apps_container.grid_columnconfigure(column, weight=1, uniform="app_categories")

        for index, (category, app_names) in enumerate(categories.items()):
            row = index // column_count
            column = index % column_count
            bg_color, border_color = CATEGORY_STYLES[index % len(CATEGORY_STYLES)]

            category_frame = ctk.CTkFrame(
                self.apps_container,
                fg_color=bg_color,
                border_width=1,
                border_color=border_color,
                corner_radius=8,
            )
            category_frame.grid(row=row, column=column, padx=8, pady=8, sticky="nsew")
            category_frame.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                category_frame,
                text=category.upper(),
                text_color=CYAN,
                anchor="w",
                font=ctk.CTkFont(size=13, weight="bold"),
            ).grid(row=0, column=0, padx=10, pady=(10, 6), sticky="ew")

            ctk.CTkFrame(category_frame, fg_color=border_color, height=1, corner_radius=0).grid(
                row=1,
                column=0,
                padx=10,
                pady=(0, 6),
                sticky="ew",
            )

            for app_row_index, app_key in enumerate(app_names, start=2):
                self.add_app_row(category_frame, app_row_index, app_key, app_key, processes)

    def add_app_row(self, parent, row, app_key, display_name, processes):
        app_key = normalize_text(app_key)
        has_process = app_key in processes
        try:
            running = is_app_running(app_key) if has_process else False
        except Exception:
            running = False
        action_text = "Zamknij" if running else "Otwórz"
        if self.is_phone_control_mode():
            running = False
            action_text = "Telefon"
        fg_color = PANEL
        hover_color = BLUE
        text_color = RED if running else GREEN
        action = "close" if running else "open"

        app_row = ctk.CTkFrame(parent, fg_color="#05070d", corner_radius=6)
        app_row.grid(row=row, column=0, padx=8, pady=4, sticky="ew")
        app_row.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            app_row,
            text=display_name,
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, padx=(10, 6), pady=8, sticky="ew")

        button = ctk.CTkButton(
            app_row,
            text=action_text,
            command=lambda target=app_key, action=action: self.run_app_action(target, action),
            width=78,
            height=28,
            fg_color=fg_color,
            hover_color=hover_color,
            text_color=text_color,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        button.grid(row=0, column=1, padx=(0, 8), pady=7, sticky="e")
        self.app_action_buttons[app_key] = button

    def run_app_action(self, target, action):
        target = normalize_text(target)
        print(f"App button clicked: action={action} target={target}")

        if self.is_phone_control_mode():
            self.set_status("WysyĹ‚am komendÄ™ do telefonu")
            thread = threading.Thread(
                target=self.run_phone_app_action_worker,
                args=(target,),
                daemon=True,
            )
            thread.start()
            return

        button = self.app_action_buttons.get(target)
        if button:
            button.configure(state="disabled")

        self.set_status("Wykonuję")
        thread = threading.Thread(
            target=self.run_app_action_worker,
            args=(target, action),
            daemon=True,
        )
        thread.start()

    def run_phone_app_action_worker(self, target):
        had_error = False
        button = self.app_action_buttons.get(target)
        if button:
            self.after(0, lambda: button.configure(state="disabled"))

        try:
            self.send_phone_command(target)
            message = f"WysĹ‚ano komendÄ™ do telefonu: {target}"
            self.append_from_thread(f"{self.assistant_name}: {message}")
            self.set_status_from_thread(message)
        except Exception as e:
            had_error = True
            self.set_error_status_from_thread(e)
            self.append_from_thread(f"BĹ‚Ä…d telefonu: {e}")
        finally:
            if button:
                self.after(0, lambda: button.configure(state="normal"))
            if had_error:
                self.after(2000, lambda: self.set_status(self.phone_mode_message()))

    def run_app_action_worker(self, target, action):
        had_error = False
        try:
            if action == "close":
                result = close_app(target)
                if result == "closed":
                    message = f"{self.assistant_name}: Zamykam {target}."
                elif result == "not_running":
                    message = f"{self.assistant_name}: Nie znalazłem uruchomionego procesu dla: {target}."
                else:
                    message = f"{self.assistant_name}: Nie znam aplikacji: {target}. Dodaj ją do processes.json."
            else:
                result = open_app(target)
                if result == "opened":
                    message = f"{self.assistant_name}: Otwieram aplikację: {target}"
                else:
                    message = f"{self.assistant_name}: Nie znam aplikacji: {target}. Dodaj ją do apps.json."

            self.append_from_thread(message)
        except Exception as e:
            had_error = True
            self.set_error_status_from_thread(e)
            self.append_from_thread(f"Błąd: {e}")
        finally:
            delay = 1500 if had_error else 0
            self.after(delay, lambda: self.set_status("Gotowy"))
            self.after(1000, self.refresh_apps_list)

    def run_app_action(self, target, action):
        target = normalize_text(target)
        print(f"App button clicked: action={action} target={target}")

        if self.is_phone_control_mode():
            self.set_status("Wysyłam komendę do telefonu")
            thread = threading.Thread(
                target=self.run_phone_app_action_worker,
                args=(target,),
                daemon=True,
            )
            thread.start()
            return

        button = self.app_action_buttons.get(target)
        if button:
            button.configure(state="disabled")

        self.set_status("Wykonuje")
        thread = threading.Thread(
            target=self.run_app_action_worker,
            args=(target, action),
            daemon=True,
        )
        thread.start()

    def run_phone_app_action_worker(self, target):
        had_error = False
        button = self.app_action_buttons.get(target)
        if button:
            self.after(0, lambda: button.configure(state="disabled"))

        try:
            self.send_phone_command(target)
            message = f"Wysłano komendę do telefonu: {target}"
            self.append_from_thread(f"{self.assistant_name}: {message}")
            self.set_status_from_thread(message)
            self.after(0, self.refresh_phone_status)
        except Exception as e:
            had_error = True
            self.set_error_status_from_thread(e)
            self.append_from_thread(f"Błąd telefonu: {e}")
        finally:
            if button:
                self.after(0, lambda: button.configure(state="normal"))
            if had_error:
                self.after(2000, lambda: self.set_status(self.phone_mode_message()))

    def build_center(self, parent):
        core_frame = ctk.CTkFrame(parent, fg_color=PANEL_2, corner_radius=8)
        core_frame.grid(row=0, column=0, padx=14, pady=14, sticky="ew")
        core_frame.grid_columnconfigure(0, weight=1)

        self.core_canvas = tk.Canvas(
            core_frame,
            width=420,
            height=285,
            bg=PANEL_2,
            highlightthickness=0,
            bd=0,
        )
        self.core_canvas.grid(row=0, column=0, pady=12)
        self.core_canvas.bind("<Configure>", self.draw_core)
        self.draw_core()

        self.history = ctk.CTkTextbox(
            parent,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=13),
            text_color=TEXT,
            fg_color="#05070d",
            border_width=1,
            border_color="#1b4f6b",
            corner_radius=8,
        )
        self.history.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="nsew")
        self.history.configure(state="disabled")

    def build_system_status(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            parent,
            text="STATUS SYSTEMU",
            text_color=CYAN,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=(16, 12), sticky="ew")

        clock_frame = ctk.CTkFrame(
            parent,
            fg_color="#0f1b2d",
            border_width=1,
            border_color=LINE,
            corner_radius=8,
        )
        clock_frame.grid(row=1, column=0, padx=14, pady=(0, 10), sticky="ew")
        clock_frame.grid_columnconfigure(0, weight=1)

        self.time_label = ctk.CTkLabel(
            clock_frame,
            text="--:--:--",
            text_color=CYAN,
            font=ctk.CTkFont(family="Consolas", size=24, weight="bold"),
        )
        self.time_label.grid(row=0, column=0, padx=10, pady=(10, 0), sticky="ew")

        self.date_label = ctk.CTkLabel(
            clock_frame,
            text="---- -- --",
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=12),
        )
        self.date_label.grid(row=1, column=0, padx=10, pady=(0, 10), sticky="ew")

        self.build_lm_studio_status(parent, 2)
        self.add_status_row(parent, 3, "Tryb głosu", "Nieznany")
        self.add_status_row(parent, 4, "Mikrofon", "Nieznany")
        self.add_status_row(parent, 5, "CPU", "brak danych")
        self.add_status_row(parent, 6, "RAM", "brak danych")
        self.build_phone_status(parent, 7)

        ctk.CTkLabel(
            parent,
            text="HUD LINK ACTIVE",
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
        ).grid(row=8, column=0, padx=14, pady=(18, 0), sticky="s")

    def build_lm_studio_status(self, parent, row):
        frame = ctk.CTkFrame(
            parent,
            fg_color="#0f1b2d",
            border_width=1,
            border_color=LINE,
            corner_radius=8,
        )
        frame.grid(row=row, column=0, padx=14, pady=(0, 10), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="LM STUDIO",
            text_color=CYAN,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")

        self.lm_server_label = ctk.CTkLabel(
            frame,
            text="Server: Nieznany",
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self.lm_server_label.grid(row=1, column=0, padx=10, pady=(0, 3), sticky="ew")

        self.lm_model_label = ctk.CTkLabel(
            frame,
            text="Model: brak",
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self.lm_model_label.grid(row=2, column=0, padx=10, pady=(0, 8), sticky="ew")

        refresh_button = ctk.CTkButton(
            frame,
            text="Odśwież status",
            command=self.refresh_lm_studio_status,
            height=28,
            fg_color="#0b1220",
            hover_color="#2f7dff",
            text_color=TEXT,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        refresh_button.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="ew")

    def build_phone_status(self, parent, row):
        frame = ctk.CTkFrame(
            parent,
            fg_color="#0f1b2d",
            border_width=1,
            border_color=LINE,
            corner_radius=8,
        )
        frame.grid(row=row, column=0, padx=14, pady=(0, 10), sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="TELEFON",
            text_color=CYAN,
            anchor="w",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")

        self.phone_status_label = ctk.CTkLabel(
            frame,
            text="Telefon: Offline",
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self.phone_status_label.grid(row=1, column=0, padx=10, pady=(0, 3), sticky="ew")

        self.phone_seen_label = ctk.CTkLabel(
            frame,
            text="Ostatnio widziany: brak",
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self.phone_seen_label.grid(row=2, column=0, padx=10, pady=(0, 3), sticky="ew")

        self.phone_command_label = ctk.CTkLabel(
            frame,
            text="Ostatnia komenda: brak",
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(size=12),
        )
        self.phone_command_label.grid(row=3, column=0, padx=10, pady=(0, 8), sticky="ew")

        refresh_button = ctk.CTkButton(
            frame,
            text="Odswiez telefon",
            command=self.refresh_phone_status,
            height=28,
            fg_color="#0b1220",
            hover_color="#2f7dff",
            text_color=TEXT,
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=12, weight="bold"),
        )
        refresh_button.grid(row=4, column=0, padx=10, pady=(0, 10), sticky="ew")

    def add_status_row(self, parent, row, name, value):
        frame = ctk.CTkFrame(parent, fg_color="#0f1b2d", corner_radius=6)
        frame.grid(row=row, column=0, padx=14, pady=6, sticky="ew")
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text=name.upper(),
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=0, column=0, padx=10, pady=(8, 0), sticky="ew")

        value_label = ctk.CTkLabel(
            frame,
            text=value,
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(size=13),
        )
        value_label.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")
        self.system_labels[name] = value_label

    def draw_core(self, _event=None):
        if self.visual_mode == "transition_to_wave":
            progress = self.ease_progress(self.visual_transition_progress)
            if progress < 0.58:
                self.draw_core_frame(1 - progress / 0.58)
            else:
                self.draw_wave_frame((progress - 0.58) / 0.42, self.wave_phase)
            return

        if self.visual_mode == "wave":
            self.draw_wave_frame(1, self.wave_phase)
            return

        if self.visual_mode == "transition_to_core":
            progress = self.ease_progress(self.visual_transition_progress)
            if progress < 0.58:
                self.draw_wave_frame(self.wave_return_start_progress * (1 - progress / 0.58), self.wave_phase)
            else:
                self.draw_core_frame((progress - 0.58) / 0.42)
            return

        self.draw_core_frame(1)

    def draw_core_frame(self, progress):
        progress = self.clamp(progress)

        canvas = self.core_canvas
        canvas.delete("all")

        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), 285)
        cx = width / 2
        cy = height / 2
        pulse = 1 + math.sin(self.pulse_phase / 10) * 0.05
        radius = min(width, height) * (0.31 + 0.05 * progress) * pulse

        line_color = self.fade_color(LINE, progress)
        canvas.create_line(22, 28, width * 0.28, 28, fill=line_color, width=max(1, int(1 + progress)))
        canvas.create_line(width * 0.72, 28, width - 22, 28, fill=line_color, width=max(1, int(1 + progress)))
        canvas.create_line(22, height - 28, width * 0.28, height - 28, fill=line_color, width=max(1, int(1 + progress)))
        canvas.create_line(width * 0.72, height - 28, width - 22, height - 28, fill=line_color, width=max(1, int(1 + progress)))

        for scale, color, line_width in [
            (1.18, "#1b4f6b", 1),
            (1.0, CYAN, 2),
            (0.82, "#2f7dff", 1),
            (0.62, BLUE, 2),
            (0.42, "#00eaff", 1),
            (0.23, "#d7f7ff", 1),
        ]:
            r = radius * scale
            canvas.create_oval(
                cx - r,
                cy - r,
                cx + r,
                cy + r,
                outline=self.fade_color(color, progress),
                width=max(1, int(line_width * max(0.6, progress))),
            )

        for angle in range(0, 360, 30):
            radians = math.radians(angle + self.pulse_phase * 1.4)
            inner = radius * 1.02
            outer = radius * 1.22
            x1 = cx + math.cos(radians) * inner
            y1 = cy + math.sin(radians) * inner
            x2 = cx + math.cos(radians) * outer
            y2 = cy + math.sin(radians) * outer
            canvas.create_line(x1, y1, x2, y2, fill=self.fade_color(CYAN, progress), width=max(1, int(progress * 2)))

        for angle in range(0, 360, 90):
            radians = math.radians(angle - self.pulse_phase)
            arc_radius = radius * 0.72
            x = cx + math.cos(radians) * arc_radius
            y = cy + math.sin(radians) * arc_radius
            dot_radius = max(1, 3 * progress)
            canvas.create_oval(
                x - dot_radius,
                y - dot_radius,
                x + dot_radius,
                y + dot_radius,
                fill=self.fade_color(CYAN, progress),
                outline="",
            )

        canvas.create_text(cx, cy - 10, text="CORE", fill=self.fade_color(TEXT, progress), font=("Segoe UI", 24, "bold"))
        canvas.create_text(cx, cy + 22, text="ONLINE", fill=self.fade_color(CYAN, progress), font=("Segoe UI", 14, "bold"))
        canvas.create_line(26, height - 24, width - 26, height - 24, fill=self.fade_color("#1b4f6b", progress), width=1)
        canvas.create_text(width - 58, height - 40, text="PULSE", fill=self.fade_color(MUTED, progress), font=("Consolas", 10))

    def draw_wave_frame(self, progress, motion_phase):
        progress = self.clamp(progress)
        speed = self.get_animation_speed()
        canvas = self.core_canvas
        canvas.delete("all")

        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), 285)
        cx = width / 2
        cy = height / 2
        palette = [CYAN, "#2f7dff", "#8a5cff", "#8a5cff"]

        frame_color = self.fade_color("#1b4f6b", progress)
        canvas.create_line(22, 28, width * 0.28, 28, fill=frame_color, width=1)
        canvas.create_line(width * 0.72, 28, width - 22, 28, fill=frame_color, width=1)
        canvas.create_line(22, height - 28, width * 0.28, height - 28, fill=frame_color, width=1)
        canvas.create_line(width * 0.72, height - 28, width - 22, height - 28, fill=frame_color, width=1)

        bar_count = 22
        visible_bars = max(2, int(bar_count * progress))
        bar_gap = 6
        available_width = width - 70
        bar_width = max(4, (available_width - bar_gap * (bar_count - 1)) / bar_count)
        start_x = (width - (bar_count * bar_width + (bar_count - 1) * bar_gap)) / 2
        for index in range(bar_count):
            if index >= visible_bars:
                continue

            phase = motion_phase * 0.18 * speed - index * 0.42
            life = (math.sin(phase) + 1) / 2
            height_scale = 0.22 + life * math.sin(life * math.pi) * 0.78
            edge_distance = min(index + 1, visible_bars - index)
            edge_envelope = self.clamp(edge_distance / 4)
            bar_height = (8 + height_scale * 102) * progress * edge_envelope
            x1 = start_x + index * (bar_width + bar_gap)
            x2 = x1 + bar_width
            color = self.fade_color(palette[index % len(palette)], progress * edge_envelope)
            canvas.create_rectangle(
                x1,
                cy - bar_height / 2,
                x2,
                cy + bar_height / 2,
                fill=color,
                outline="",
            )

        canvas.create_text(cx, 54, text="LISTENING", fill=self.fade_color(CYAN, progress), font=("Segoe UI", 18, "bold"))
        canvas.create_text(
            cx,
            height - 48,
            text="AUDIO INPUT ACTIVE",
            fill=self.fade_color("#8a5cff", progress),
            font=("Consolas", 11, "bold"),
        )
        canvas.create_line(26, height - 24, width - 26, height - 24, fill=self.fade_color("#2f7dff", progress), width=1)

    def start_core_to_wave_transition(self):
        self.visual_mode = "transition_to_wave"
        self.visual_transition_progress = 0.0
        self.wave_phase = 0
        self.draw_core()

    def start_wave_to_core_transition(self):
        if self.visual_mode == "core":
            return

        self.wave_return_start_progress = 1.0
        if self.visual_mode == "transition_to_wave":
            progress = self.ease_progress(self.visual_transition_progress)
            if progress < 0.58:
                self.wave_return_start_progress = 0.0
            else:
                self.wave_return_start_progress = (progress - 0.58) / 0.42
        elif self.visual_mode == "transition_to_core":
            return

        if self.wave_return_start_progress <= 0:
            self.visual_mode = "core"
            self.visual_transition_progress = 0.0
            self.draw_core()
            return

        self.visual_mode = "transition_to_core"
        self.visual_transition_progress = 0.0
        self.draw_core()

    def clamp(self, value):
        return max(0.0, min(1.0, value))

    def get_animation_speed(self):
        if not self.config:
            return 1.6

        try:
            speed = float(self.config.get("animation_speed", 1.6))
        except (TypeError, ValueError):
            return 1.6

        return self.clamp_animation_speed(speed)

    def clamp_animation_speed(self, speed):
        return max(0.5, min(3.0, speed))

    def ease_progress(self, value):
        value = self.clamp(value)
        return value * value * (3 - 2 * value)

    def fade_color(self, color, progress):
        progress = self.clamp(progress)
        color = color.lstrip("#")
        red = int(color[0:2], 16)
        green = int(color[2:4], 16)
        blue = int(color[4:6], 16)
        base_red = int(PANEL_2[1:3], 16)
        base_green = int(PANEL_2[3:5], 16)
        base_blue = int(PANEL_2[5:7], 16)
        red = int(base_red + (red - base_red) * progress)
        green = int(base_green + (green - base_green) * progress)
        blue = int(base_blue + (blue - base_blue) * progress)
        return f"#{red:02x}{green:02x}{blue:02x}"

    def animate_core(self):
        animation_speed = self.get_animation_speed()
        self.pulse_phase = (self.pulse_phase + 1) % 360
        if self.visual_mode in ["transition_to_wave", "wave", "transition_to_core"]:
            self.wave_phase = (self.wave_phase + animation_speed) % 10000

        if self.visual_mode == "transition_to_wave":
            self.visual_transition_progress += 0.075 * animation_speed
            if self.visual_transition_progress >= 1:
                self.visual_transition_progress = 1
                self.visual_mode = "wave"
        elif self.visual_mode == "transition_to_core":
            self.visual_transition_progress += 0.075 * animation_speed
            if self.visual_transition_progress >= 1:
                self.visual_transition_progress = 0
                self.visual_mode = "core"

        if hasattr(self, "core_canvas"):
            self.draw_core()
        self.after(80, self.animate_core)

    def load_jarvis(self):
        try:
            self.config = load_config()
            self.assistant_name = self.config["assistant_name"]
            self.client = create_client(self.config)
            self.messages = create_messages(self.config)
            self.update_system_status("Gotowy")
            self.refresh_lm_studio_status()
            self.refresh_phone_status()
            self.after(5000, self.refresh_phone_status_periodic)
            self.append_history(f"{self.assistant_name} uruchomiony.")
        except ConfigError as e:
            self.set_error_status(e)
            self.update_system_status("Błąd")
            self.append_history(f"Błąd konfiguracji: {e}")
            self.set_controls_enabled(False)
        except Exception as e:
            self.set_error_status(e)
            self.update_system_status("Błąd")
            self.append_history(f"Błąd uruchamiania GUI: {e}")
            self.set_controls_enabled(False)

    def update_system_status(self, lm_status=None):
        if not self.config:
            return

        values = {
            "Tryb głosu": "Włączony" if self.config.get("voice_enabled", False) else "Wyłączony",
            "Mikrofon": f"Urządzenie {self.config.get('microphone_device', 'auto')}",
        }

        for name, value in values.items():
            label = self.system_labels.get(name)
            if label:
                label.configure(text=str(value))

    def refresh_lm_studio_status(self):
        if self.lm_server_label:
            self.lm_server_label.configure(text="Server: Sprawdzam...")
        if self.lm_model_label:
            self.lm_model_label.configure(text="Model: Sprawdzam...")

        thread = threading.Thread(target=self.refresh_lm_studio_status_worker, daemon=True)
        thread.start()

    def refresh_lm_studio_status_worker(self):
        expected_model = "local-model"
        if self.config:
            expected_model = self.config.get("model", expected_model)

        server_text = "Server: Offline"
        model_text = "Model: brak"

        try:
            if requests is None:
                raise RuntimeError("requests is not installed")

            response = requests.get("http://127.0.0.1:1233/v1/models", timeout=2)
            response.raise_for_status()
            data = response.json()
            models = data.get("data", []) if isinstance(data, dict) else []
            model_ids = {
                model.get("id")
                for model in models
                if isinstance(model, dict) and isinstance(model.get("id"), str)
            }

            server_text = "Server: Online"
            if expected_model in model_ids:
                model_text = f"Model: {expected_model} aktywny"
        except Exception:
            pass

        self.after(0, lambda: self.update_lm_studio_labels(server_text, model_text))

    def update_lm_studio_labels(self, server_text, model_text):
        if self.lm_server_label:
            self.lm_server_label.configure(text=server_text)
        if self.lm_model_label:
            self.lm_model_label.configure(text=model_text)

    def refresh_phone_status(self):
        if self.phone_status_label:
            self.phone_status_label.configure(text="Telefon: Sprawdzam...")

        thread = threading.Thread(target=self.refresh_phone_status_worker, daemon=True)
        thread.start()

    def refresh_phone_status_periodic(self):
        self.refresh_phone_status()
        self.after(5000, self.refresh_phone_status_periodic)

    def refresh_phone_status_worker(self):
        status_text = "Telefon: Offline"
        seen_text = "Ostatnio widziany: brak"
        command_text = "Ostatnia komenda: brak"

        try:
            if requests is None:
                raise RuntimeError("requests is not installed")
            if not self.config:
                raise RuntimeError("brak konfiguracji")

            token = self.config.get("api_token")
            if not token:
                raise RuntimeError("brak api_token")

            response = requests.get(
                "http://127.0.0.1:8000/phone/status",
                headers={"X-Jarvis-Token": token},
                timeout=2,
            )
            if response.status_code == 401:
                raise RuntimeError("token API odrzucony")
            response.raise_for_status()

            data = response.json()
            status_text = "Telefon: Online" if data.get("online") else "Telefon: Offline"
            seen_text = f"Ostatnio widziany: {data.get('last_seen') or 'brak'}"
            command_text = f"Ostatnia komenda: {data.get('last_command') or 'brak'}"
        except Exception as e:
            status_text = "Telefon: Blad"
            seen_text = "Ostatnio widziany: brak"
            command_text = f"Ostatnia komenda: {str(e).splitlines()[0][:32]}"

        self.after(
            0,
            lambda: self.update_phone_status_labels(status_text, seen_text, command_text),
        )

    def update_phone_status_labels(self, status_text, seen_text, command_text):
        if self.phone_status_label:
            self.phone_status_label.configure(text=status_text)
        if self.phone_seen_label:
            self.phone_seen_label.configure(text=seen_text)
        if self.phone_command_label:
            self.phone_command_label.configure(text=command_text)

    def update_clock_and_metrics(self):
        now = datetime.datetime.now()

        if hasattr(self, "time_label"):
            self.time_label.configure(text=now.strftime("%H:%M:%S"))
        if hasattr(self, "date_label"):
            self.date_label.configure(text=now.strftime("%Y-%m-%d"))

        cpu_label = self.system_labels.get("CPU")
        ram_label = self.system_labels.get("RAM")

        if psutil is None:
            if cpu_label:
                cpu_label.configure(text="brak danych")
            if ram_label:
                ram_label.configure(text="brak danych")
        else:
            try:
                cpu = psutil.cpu_percent(interval=None)
                ram = psutil.virtual_memory().percent
                if cpu_label:
                    cpu_label.configure(text=f"{cpu:.0f}%")
                if ram_label:
                    ram_label.configure(text=f"{ram:.0f}%")
            except Exception:
                if cpu_label:
                    cpu_label.configure(text="brak danych")
                if ram_label:
                    ram_label.configure(text="brak danych")

        self.after(1000, self.update_clock_and_metrics)

    def toggle_fullscreen(self, _event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.attributes("-fullscreen", self.is_fullscreen)
        return "break"

    def exit_fullscreen(self, _event=None):
        if self.is_fullscreen:
            self.is_fullscreen = False
            self.attributes("-fullscreen", False)
        return "break"

    def close_window(self):
        self.destroy()

    def is_phone_control_mode(self):
        return self.control_mode == "phone"

    def set_control_mode(self, value):
        self.control_mode = "phone" if value == "Steruj telefonem" else "pc"
        if self.is_phone_control_mode():
            message = self.phone_mode_message()
            self.set_status(message)
            if hasattr(self, "history"):
                self.append_history(f"{self.assistant_name}: {message}")
            if self.apps_panel_visible:
                self.refresh_apps_list()
            return

        self.set_status("Gotowy")
        if self.apps_panel_visible:
            self.refresh_apps_list()

    def handle_phone_mode_request(self):
        message = self.phone_mode_message()
        output = f"{self.assistant_name}: {message}"
        self.append_history(output)
        self.set_status(message)
        self.speak_in_background(message)

    def phone_mode_message(self):
        return "Tryb telefonu aktywny."

    def send_phone_command(self, target):
        if requests is None:
            raise RuntimeError("requests is not installed")
        if not self.config:
            raise RuntimeError("Brak konfiguracji Jarvisa")

        token = self.config.get("api_token")
        if not token:
            raise RuntimeError("Brak api_token w config.json")

        response = requests.post(
            "http://127.0.0.1:8000/phone/command",
            json={
                "action": "open_mobile_app",
                "target": target,
            },
            headers={"X-Jarvis-Token": token},
            timeout=3,
        )

        if response.status_code == 401:
            raise RuntimeError("Nieautoryzowany token API")

        response.raise_for_status()
        return response.json()

    def set_status(self, status):
        self.status_label.configure(text=status)

    def set_error_status(self, detail=None):
        status = "Błąd"
        if detail:
            status = f"Błąd: {str(detail).splitlines()[0][:48]}"
        self.set_status(status)

    def set_error_status_from_thread(self, detail=None):
        self.after(0, lambda: self.set_error_status(detail))

    def set_controls_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.entry.configure(state=state)
        self.send_button.configure(state=state)
        self.listen_button.configure(state=state)
        self.is_busy = not enabled

    def set_text_controls_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.entry.configure(state=state)
        self.send_button.configure(state=state)

    def on_entry_return(self, event):
        if event.state & 0x0001:
            self.entry.insert("insert", "\n")
            return "break"

        self.send_text()
        return "break"

    def on_entry_shift_return(self, _event):
        self.entry.insert("insert", "\n")
        return "break"

    def append_history(self, text):
        if not text:
            return

        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        lines = [line for line in text.rstrip().splitlines() if line.strip()]
        formatted_text = "".join(f"[{timestamp}] {line}\n" for line in lines)

        self.history.configure(state="normal")
        self.history.insert("end", formatted_text)
        self.history.see("end")
        self.history.configure(state="disabled")

    def clear_history(self):
        self.history.configure(state="normal")
        self.history.delete("1.0", "end")
        self.history.configure(state="disabled")

    def append_from_thread(self, text):
        self.after(0, lambda: self.append_history(text))

    def set_status_from_thread(self, status):
        self.after(0, lambda: self.set_status(status))

    def finish_work(self):
        self.set_controls_enabled(True)
        if self.is_phone_control_mode():
            self.set_status(self.phone_mode_message())
        else:
            self.set_status("Gotowy")
        self.entry.focus_set()

    def capture_output(self, callback):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = callback()

        return result, output.getvalue().strip()

    def send_text(self):
        if self.is_busy:
            return

        user_text = self.entry.get("1.0", "end-1c").strip()
        if not user_text:
            return

        self.entry.delete("1.0", "end")
        self.submit_user_text(user_text)

    def submit_user_text(self, user_text):
        if user_text.lower() == "/listen":
            self.append_history("Przytrzymaj przycisk Listen, aby nagrywać.")
            return

        self.append_history(f"Ty: {user_text}")
        if self.is_phone_control_mode():
            self.handle_phone_mode_request()
            return

        self.set_controls_enabled(False)

        status = "Wykonuję" if self.is_local_action(user_text) else "Myślę..."
        self.set_status(status)

        thread = threading.Thread(target=self.run_text_worker, args=(user_text,), daemon=True)
        thread.start()

    def is_local_action(self, text):
        if text.startswith("/"):
            return True

        if self.pending_note_content is not None:
            return True

        return parse_local_action(text) is not None

    def run_text_worker(self, user_text):
        had_error = False
        try:
            should_exit, output, tts_text = self.process_user_text_for_gui(user_text)
            self.append_from_thread(output)
            if output and output.startswith("Błąd:"):
                had_error = True
                self.set_error_status_from_thread(output[len("Błąd:") :].strip())
            self.speak_in_background(tts_text)

            if should_exit:
                self.after(300, self.destroy)
                return
        except Exception as e:
            had_error = True
            self.set_error_status_from_thread(e)
            self.append_from_thread(f"Błąd: {e}")
        finally:
            self.after(1500 if had_error else 0, self.finish_work)

    def on_listen_press(self, _event):
        if self.is_busy:
            return

        self.is_busy = True
        self.is_recording = True
        self.set_text_controls_enabled(False)
        self.set_status("Słucham")
        self.start_core_to_wave_transition()

        try:
            from speech_input import start_recording

            started, output = self.capture_output(start_recording)
            self.append_history(output)

            if not started:
                self.is_recording = False
                self.start_wave_to_core_transition()
                self.finish_work()
        except Exception as e:
            self.set_error_status(e)
            self.append_history(f"Błąd: {e}")
            self.is_recording = False
            self.start_wave_to_core_transition()
            self.after(1500, self.finish_work)

    def on_listen_release(self, _event):
        if not self.is_recording:
            return

        self.is_recording = False
        self.start_wave_to_core_transition()
        self.listen_button.configure(state="disabled")
        self.set_status("Rozpoznaję")

        thread = threading.Thread(target=self.listen_release_worker, daemon=True)
        thread.start()

    def listen_release_worker(self):
        had_error = False
        try:
            from speech_input import stop_recording_and_transcribe

            spoken_text, listen_output = self.capture_output(stop_recording_and_transcribe)
            self.append_from_thread(listen_output)

            if not spoken_text:
                return

            self.append_from_thread(f"Ty: {spoken_text}")
            if self.is_phone_control_mode():
                message = self.phone_mode_message()
                self.append_from_thread(f"{self.assistant_name}: {message}")
                self.set_status_from_thread(message)
                self.speak_in_background(message)
                return
            status = "Wykonuję" if self.is_local_action(spoken_text) else "Myślę..."
            self.set_status_from_thread(status)

            _should_exit, output, tts_text = self.process_user_text_for_gui(spoken_text)
            self.append_from_thread(output)
            if output and output.startswith("Błąd:"):
                had_error = True
                self.set_error_status_from_thread(output[len("Błąd:") :].strip())
            self.speak_in_background(tts_text)
        except Exception as e:
            had_error = True
            self.set_error_status_from_thread(e)
            self.append_from_thread(f"Błąd: {e}")
        finally:
            self.after(1500 if had_error else 0, self.finish_work)

    def process_user_text_for_gui(self, user_input):
        if user_input.startswith("/"):
            from main import handle_local_command

            should_exit, output = self.capture_output(
                lambda: handle_local_command(
                    user_input.strip().lower(),
                    self.assistant_name,
                    self.client,
                    self.config,
                    self.messages,
                )
            )
            return should_exit, output, None

        normalized_user_input = normalize_text(user_input)

        if self.pending_note_content is not None:
            if normalized_user_input in ["anuluj", "cancel"]:
                self.pending_note_content = None
                return False, f"{self.assistant_name}: Anulowano notatkę.", "Anulowano notatkę."

            title = user_input.strip()
            if not title:
                question = "Jaki ma być tytuł notatki?"
                return False, f"{self.assistant_name}: {question}", question

            try:
                result = create_note(self.pending_note_content, title)
            except Exception as e:
                return False, f"Błąd: {e}", None

            self.pending_note_content = None
            if result == "saved":
                self.after(0, self.refresh_notes_list)
                return False, f"{self.assistant_name}: Notatka zapisana.", "Notatka zapisana."

            return False, f"{self.assistant_name}: Brakuje treści notatki.", None

        normalized_exit_commands = [
            normalize_text(command) for command in self.config["exit_commands"]
        ]

        if normalized_user_input in normalized_exit_commands:
            return True, f"{self.assistant_name}: Wyłączam się. Do zobaczenia!", None

        local_action = parse_local_action(user_input)
        if local_action:
            if local_action.get("action") == "create_note" and local_action.get("needs_title"):
                content = local_action.get("content", "").strip()
                if not content:
                    return False, f"{self.assistant_name}: Brakuje treści notatki.", None

                self.pending_note_content = content
                question = "Jaki ma być tytuł notatki?"
                return False, f"{self.assistant_name}: {question}", question

            import json
            from main import handle_ai_answer

            _result, output = self.capture_output(
                lambda: handle_ai_answer(
                    json.dumps(local_action),
                    self.assistant_name,
                    self.config,
                )
            )
            if local_action.get("action") == "create_note":
                self.after(0, self.refresh_notes_list)
            return False, output, None

        add_user_message(self.messages, normalized_user_input)

        try:
            from ai_client import get_ai_response

            answer = get_ai_response(self.client, self.messages, self.config)
            if not answer or not answer.strip():
                response = "Nie otrzymałem odpowiedzi."
                add_assistant_message(self.messages, response)
                return False, f"{self.assistant_name}: {response}", response

            output, tts_text = self.handle_ai_answer_for_gui(answer)
            add_assistant_message(self.messages, answer)
            return False, output, tts_text
        except Exception as e:
            return False, f"Błąd: {e}", None

    def handle_ai_answer_for_gui(self, answer):
        data = parse_ai_json(answer)
        action = data.get("action")

        if action == "chat":
            response = data.get("response", "")
            return f"{self.assistant_name}: {response}", response

        if action == "create_note" and (data.get("needs_title") or not str(data.get("title") or "").strip()):
            content = str(data.get("content") or "").strip()
            if not content:
                return f"{self.assistant_name}: Brakuje treści notatki.", None

            self.pending_note_content = content
            question = "Jaki ma być tytuł notatki?"
            return f"{self.assistant_name}: {question}", question

        from main import handle_ai_answer

        _result, output = self.capture_output(
            lambda: handle_ai_answer(answer, self.assistant_name, self.config)
        )
        if action == "create_note":
            self.after(0, self.refresh_notes_list)
        return output, None

    def speak_in_background(self, text):
        if not text or not self.config.get("voice_enabled", False):
            return

        def worker():
            try:
                from voice import speak

                speak(text)
            except Exception as e:
                self.set_error_status_from_thread(e)
                self.after(1500, lambda: self.set_status("Gotowy"))
                try:
                    print("Błąd TTS:", e, file=sys.__stderr__ or sys.stderr)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = JarvisGUI()
    app.mainloop()
