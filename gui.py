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


BG = "#020713"
PANEL = "#030a15"
PANEL_2 = "#061323"
CYAN = "#77d7e8"
BLUE = "#2b668f"
PURPLE = "#7967b8"
GREEN = "#43d7b3"
GREEN_HOVER = "#2da984"
RED = "#d24b63"
RED_HOVER = "#a93b51"
TEXT = "#e2f5ff"
MUTED = "#8faec3"
LINE = "#0d2b3f"
PLACEHOLDER = "#6f8ca1"
HUD_SCALE_OPTIONS = ["1.15", "1.30", "1.45"]
RADIUS = 6
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

        self.title("Jarvis Desktop")
        self.geometry("1440x820")
        self.minsize(1080, 680)
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
        self.core_state = "READY"
        self.system_labels = {}
        self.status_dots = {}
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
        self.active_view = "chat"
        self.view_frames = {}
        self.text_scale = 1.0
        self.hud_scale = 1.0
        self.show_system_status = True
        self.entry_placeholder = "Wiadomość lub komenda..."
        self.entry_placeholder_active = False

        self.bind("<F11>", self.toggle_fullscreen)
        self.bind("<Escape>", self.exit_fullscreen)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.bg_canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self.tk.call("lower", self.bg_canvas._w)
        self.bg_canvas.bind("<Configure>", self.draw_root_grid)

        self.build_header()
        self.build_dashboard()
        self.build_input_bar()
        self.load_jarvis()
        self.update_clock_and_metrics()
        self.animate_core()

    def build_header(self):
        header = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        header.grid(row=0, column=0, padx=10, pady=(8, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)
        header.grid_columnconfigure(2, weight=0)

        self.title_label = ctk.CTkLabel(
            header,
            text="JARVIS DESKTOP",
            text_color=TEXT,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
        )
        self.title_label.grid(row=0, column=0, sticky="w")

        tabs = ctk.CTkFrame(header, fg_color="transparent")
        tabs.grid(row=1, column=0, pady=(8, 0), sticky="w")

        self.chat_tab_button = self.create_tab_button(tabs, "CHAT", lambda: self.show_view("chat"))
        self.chat_tab_button.configure(fg_color="#061827", text_color=CYAN, state="disabled")
        self.chat_tab_button.grid(row=0, column=0, padx=(0, 8), sticky="w")

        self.apps_toggle_button = self.create_tab_button(tabs, "APLIKACJE", lambda: self.show_view("apps"))
        self.apps_toggle_button.grid(row=0, column=1, padx=(0, 8), sticky="w")

        self.notes_toggle_button = self.create_tab_button(tabs, "NOTATKI", lambda: self.show_view("notes"))
        self.notes_toggle_button.grid(row=0, column=2, padx=(0, 8), sticky="w")

        self.settings_button = self.create_tab_button(tabs, "USTAWIENIA", lambda: self.show_view("settings"))
        self.settings_button.grid(row=0, column=3, sticky="w")

        self.status_label = ctk.CTkLabel(
            header,
            text="READY",
            text_color=GREEN,
            anchor="e",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
        )

        self.close_button = ctk.CTkButton(
            header,
            text="X",
            command=self.close_window,
            width=28,
            height=22,
            fg_color="#030b16",
            hover_color="#102c40",
            text_color=RED,
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
            font=ctk.CTkFont(size=10, weight="bold"),
        )
        self.close_button.grid(row=0, column=2, padx=(10, 0), sticky="ne")

    def build_dashboard(self):
        self.dashboard = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.dashboard.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")
        self.dashboard.grid_columnconfigure(0, weight=0, minsize=220)
        self.dashboard.grid_columnconfigure(1, weight=1)
        self.dashboard.grid_columnconfigure(2, weight=0, minsize=300)
        self.dashboard.grid_rowconfigure(0, weight=1)

        self.left_panel = self.create_panel(self.dashboard)
        self.left_panel.grid(row=0, column=0, padx=(0, 12), sticky="nsew")
        self.build_system_status(self.left_panel)

        self.center_panel = ctk.CTkFrame(self.dashboard, fg_color=BG, corner_radius=0)
        self.center_panel.grid(row=0, column=1, padx=0, sticky="nsew")
        self.center_panel.grid_columnconfigure(0, weight=1)
        self.center_panel.grid_rowconfigure(0, weight=1)
        self.build_center(self.center_panel)

        self.right_panel = self.create_panel(self.dashboard)
        self.right_panel.grid(row=0, column=2, padx=(12, 0), sticky="nsew")
        self.build_console_panel(self.right_panel)

    def build_input_bar_legacy(self):
        self.input_frame = ctk.CTkFrame(
            self,
            fg_color="#030a14",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
        )
        self.input_frame.grid(row=2, column=0, padx=112, pady=(0, 12), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.input_frame,
            text="COMMAND INPUT",
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
        ).grid(row=0, column=0, columnspan=4, padx=10, pady=(5, 0), sticky="ew")

        self.entry = ctk.CTkTextbox(
            self.input_frame,
            height=34,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=TEXT,
            fg_color="#020713",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
        )
        self.entry.grid(row=1, column=0, padx=(10, 8), pady=(4, 8), sticky="ew")
        self.entry.bind("<Return>", self.on_entry_return)
        self.entry.bind("<Shift-Return>", self.on_entry_shift_return)

        self.send_button = self.create_action_button(
            self.input_frame,
            "Wyślij",
            self.send_text,
            fg_color=PANEL_2,
            hover_color=BLUE,
        )
        self.send_button.configure(text="WYŚLIJ")
        self.send_button.grid(row=1, column=1, padx=(0, 7), pady=(4, 8), sticky="ew")

        self.listen_button = self.create_action_button(self.input_frame, "Listen", None)
        self.listen_button.configure(text="LISTEN")
        self.listen_button.grid(row=1, column=2, padx=(0, 7), pady=(4, 8), sticky="ew")
        self.listen_button.bind("<ButtonPress-1>", self.on_listen_press)
        self.listen_button.bind("<ButtonRelease-1>", self.on_listen_release)

        self.clear_button = self.create_action_button(
            self.input_frame,
            "Wyczyść",
            self.clear_history,
            fg_color="transparent",
            hover_color="#102c40",
        )
        self.clear_button.configure(text="CLEAR")
        self.clear_button.grid(row=1, column=3, padx=(0, 10), pady=(4, 8), sticky="ew")

    def build_input_bar(self):
        self.input_frame = ctk.CTkFrame(
            self,
            fg_color="#030a14",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
        )
        self.input_frame.grid(row=2, column=0, padx=112, pady=(0, 12), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=0)
        self.input_frame.grid_columnconfigure(1, weight=1)
        self.input_frame.grid_columnconfigure(2, weight=0)

        self.listen_button = ctk.CTkButton(
            self.input_frame,
            text="🎙",
            command=None,
            width=42,
            height=42,
            fg_color="#030b16",
            hover_color="#15102b",
            text_color="#c8b8ff",
            border_width=1,
            border_color=PURPLE,
            corner_radius=RADIUS,
            font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold"),
        )
        self.listen_button.grid(row=0, column=0, padx=(10, 8), pady=8, sticky="w")
        self.listen_button.bind("<ButtonPress-1>", self.on_listen_press)
        self.listen_button.bind("<ButtonRelease-1>", self.on_listen_release)

        self.entry = ctk.CTkTextbox(
            self.input_frame,
            height=42,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=12),
            text_color=TEXT,
            fg_color="#020713",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
        )
        self.entry.grid(row=0, column=1, padx=(0, 8), pady=8, sticky="ew")
        self.entry.bind("<Return>", self.on_entry_return)
        self.entry.bind("<Shift-Return>", self.on_entry_shift_return)
        self.entry.bind("<FocusIn>", self.on_entry_focus_in)
        self.entry.bind("<FocusOut>", self.on_entry_focus_out)
        self.entry.bind("<KeyPress>", self.on_entry_key_press)
        self.show_entry_placeholder()

        self.send_button = self.create_action_button(
            self.input_frame,
            "➤ WYŚLIJ",
            self.send_text,
            fg_color=PANEL_2,
            hover_color=BLUE,
        )
        self.send_button.configure(width=96, height=42, border_color=CYAN, corner_radius=RADIUS)
        self.send_button.grid(row=0, column=2, padx=(0, 10), pady=8, sticky="e")

    def create_panel(self, parent):
        return ctk.CTkFrame(
            parent,
            fg_color=PANEL,
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
        )

    def create_action_button(self, parent, text, command, fg_color=PANEL, hover_color=BLUE):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=86,
            height=24,
            fg_color=fg_color,
            hover_color=hover_color,
            text_color=TEXT,
            border_width=1,
            border_color=CYAN,
            corner_radius=RADIUS,
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
        )

    def create_tab_button(self, parent, text, command):
        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            width=78 if len(text) <= 5 else 104,
            height=20,
            fg_color="#030b16",
            hover_color="#0b283a",
            text_color=MUTED,
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
        )

    def ui_font(self, size, family="Consolas", weight=None):
        scaled_size = max(7, int(round(size * self.text_scale)))
        if weight:
            return ctk.CTkFont(family=family, size=scaled_size, weight=weight)
        return ctk.CTkFont(family=family, size=scaled_size)

    def apply_text_scale(self):
        if hasattr(self, "title_label"):
            self.title_label.configure(font=self.ui_font(11, weight="bold"), text_color=TEXT)
        for button in [
            getattr(self, "chat_tab_button", None),
            getattr(self, "apps_toggle_button", None),
            getattr(self, "notes_toggle_button", None),
            getattr(self, "settings_button", None),
        ]:
            if button:
                button.configure(font=self.ui_font(9, weight="bold"))
        for button in [
            getattr(self, "send_button", None),
            getattr(self, "listen_button", None),
        ]:
            if button:
                base_size = 17 if button == getattr(self, "listen_button", None) else 10
                family = "Segoe UI" if button == getattr(self, "listen_button", None) else "Consolas"
                button.configure(font=self.ui_font(base_size, family=family, weight="bold"), text_color=button.cget("text_color"))
        if hasattr(self, "entry"):
            self.entry.configure(font=self.ui_font(12), text_color=PLACEHOLDER if self.entry_placeholder_active else TEXT)
        if hasattr(self, "history"):
            self.history.configure(font=self.ui_font(11), text_color=TEXT)
        if hasattr(self, "core_state_label"):
            self.core_state_label.configure(font=self.ui_font(12, weight="bold"))
        for root in [
            getattr(self, "left_panel", None),
            getattr(self, "right_panel", None),
            getattr(self, "settings_panel", None),
            getattr(self, "notes_panel", None),
            getattr(self, "apps_panel", None),
        ]:
            if root:
                self.apply_text_scale_recursive(root)

    def apply_text_scale_recursive(self, widget):
        for child in widget.winfo_children():
            class_name = child.__class__.__name__
            try:
                if class_name == "CTkLabel":
                    child.configure(font=self.ui_font(9 if child.winfo_height() < 24 else 10, weight="bold"))
                elif class_name == "CTkButton":
                    child.configure(font=self.ui_font(9 if child.winfo_height() <= 24 else 10, weight="bold"))
                elif class_name in {"CTkEntry", "CTkTextbox"}:
                    child.configure(font=self.ui_font(11), text_color=TEXT)
                elif class_name in {"CTkCheckBox", "CTkSegmentedButton"}:
                    child.configure(font=self.ui_font(10, weight="bold"), text_color=TEXT)
            except Exception:
                pass
            self.apply_text_scale_recursive(child)

    def show_view(self, view_name):
        if not self.view_frames:
            return

        for frame in self.view_frames.values():
            frame.grid_remove()

        selected = self.view_frames.get(view_name) or self.view_frames.get("chat")
        if selected:
            selected.grid()
            selected.tkraise()

        self.active_view = view_name if view_name in self.view_frames else "chat"
        self.apps_panel_visible = self.active_view == "apps"
        self.update_tab_styles()

        if self.active_view == "apps":
            self.refresh_apps_list()
        elif self.active_view == "notes":
            self.refresh_notes_list()
        elif self.active_view == "settings":
            self.refresh_settings_view()

    def update_tab_styles(self):
        tab_map = {
            "chat": self.chat_tab_button,
            "apps": self.apps_toggle_button,
            "notes": self.notes_toggle_button,
            "settings": self.settings_button,
        }
        for name, button in tab_map.items():
            if not button:
                continue
            if name == self.active_view:
                button.configure(fg_color="#061827", text_color=CYAN, border_color=CYAN, state="normal", corner_radius=RADIUS)
            else:
                button.configure(fg_color="#030b16", text_color=MUTED, border_color=LINE, state="normal", corner_radius=RADIUS)

    def apply_system_status_visibility(self):
        if not hasattr(self, "left_panel"):
            return
        if self.show_system_status:
            self.dashboard.grid_columnconfigure(0, weight=0, minsize=220)
            self.left_panel.grid(row=0, column=0, padx=(0, 12), sticky="nsew")
        else:
            self.left_panel.grid_remove()
            self.dashboard.grid_columnconfigure(0, weight=0, minsize=0)

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
        self.show_view("notes")

    def build_notes_panel(self, parent):
        self.notes_panel = ctk.CTkFrame(
            parent,
            fg_color="transparent",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
        )
        self.notes_panel.grid(row=0, column=0, padx=14, pady=14, sticky="nsew")
        self.notes_panel.grid_columnconfigure(0, weight=0, minsize=280)
        self.notes_panel.grid_columnconfigure(1, weight=1)
        self.notes_panel.grid_rowconfigure(1, weight=1)
        self.view_frames["notes"] = self.notes_panel

        ctk.CTkLabel(
            self.notes_panel,
            text="NOTATKI",
            text_color=CYAN,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
        ).grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")

        button_row = ctk.CTkFrame(self.notes_panel, fg_color="transparent")
        button_row.grid(row=0, column=1, padx=12, pady=(12, 8), sticky="e")
        new_button = self.create_action_button(
            button_row,
            "NOWA",
            self.open_new_note_window,
            fg_color="#030b16",
            hover_color="#102c40",
        )
        new_button.grid(row=0, column=0, padx=(0, 8), sticky="e")
        refresh_button = self.create_action_button(
            button_row,
            "ODŚWIEŻ",
            self.refresh_notes_list,
            fg_color="#030b16",
            hover_color="#102c40",
        )
        refresh_button.grid(row=0, column=1, sticky="e")

        self.notes_list_frame = ctk.CTkScrollableFrame(
            self.notes_panel,
            fg_color="#020713",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
            scrollbar_button_color=BLUE,
            scrollbar_button_hover_color=CYAN,
        )
        self.notes_list_frame.grid(row=1, column=0, padx=(12, 6), pady=(0, 12), sticky="nsew")
        self.notes_list_frame.grid_columnconfigure(0, weight=1)

        self.notes_detail_frame = ctk.CTkFrame(
            self.notes_panel,
            fg_color="#020713",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
        )
        self.notes_detail_frame.grid(row=1, column=1, padx=(6, 12), pady=(0, 12), sticky="nsew")
        self.notes_detail_frame.grid_columnconfigure(0, weight=1)
        self.notes_detail_frame.grid_rowconfigure(1, weight=1)
        self.show_note_placeholder()
        self.notes_panel.grid_remove()

    def clear_notes_detail(self):
        if not hasattr(self, "notes_detail_frame"):
            return
        for widget in self.notes_detail_frame.winfo_children():
            widget.destroy()

    def show_note_placeholder(self):
        self.clear_notes_detail()
        ctk.CTkLabel(
            self.notes_detail_frame,
            text="WYBIERZ NOTATKĘ",
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=14, sticky="ew")

    def show_note_detail(self, note):
        self.clear_notes_detail()
        title = str(note.get("title") or "Bez tytułu")
        content = str(note.get("content") or "")
        created_at = self.format_note_timestamp(note.get("created_at", ""))
        note_path = note.get("path", "")

        ctk.CTkLabel(
            self.notes_detail_frame,
            text=title,
            text_color=CYAN,
            anchor="w",
            wraplength=520,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=(14, 8), sticky="ew")

        content_box = ctk.CTkTextbox(
            self.notes_detail_frame,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=TEXT,
            fg_color="#020713",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
        )
        content_box.grid(row=1, column=0, padx=14, pady=(0, 8), sticky="nsew")
        content_box.insert("1.0", content or "Brak treści")
        content_box.configure(state="disabled")

        ctk.CTkLabel(
            self.notes_detail_frame,
            text=created_at,
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=9),
        ).grid(row=2, column=0, padx=14, pady=(0, 8), sticky="ew")

        delete_button = self.create_action_button(
            self.notes_detail_frame,
            "USUŃ",
            lambda path=note_path: self.delete_note_from_gui(path),
            fg_color="#030b16",
            hover_color="#102c40",
        )
        delete_button.configure(text_color=RED)
        delete_button.grid(row=3, column=0, padx=14, pady=(0, 14), sticky="e")

    def show_new_note_form(self):
        self.clear_notes_detail()
        self.notes_detail_frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self.notes_detail_frame,
            text="NOWA NOTATKA",
            text_color=CYAN,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=(14, 8), sticky="ew")

        title_entry = ctk.CTkEntry(
            self.notes_detail_frame,
            placeholder_text="Tytuł",
            fg_color="#020713",
            text_color=TEXT,
            border_color=LINE,
            border_width=1,
            corner_radius=RADIUS,
        )
        title_entry.grid(row=1, column=0, padx=14, pady=(0, 8), sticky="ew")

        content_box = ctk.CTkTextbox(
            self.notes_detail_frame,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=TEXT,
            fg_color="#020713",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
        )
        content_box.grid(row=2, column=0, padx=14, pady=(0, 8), sticky="nsew")

        message_label = ctk.CTkLabel(
            self.notes_detail_frame,
            text="",
            text_color=GREEN_HOVER,
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
        )
        message_label.grid(row=3, column=0, padx=14, pady=(0, 8), sticky="ew")

        save_button = self.create_action_button(
            self.notes_detail_frame,
            "ZAPISZ",
            lambda: self.save_note_from_window(title_entry, content_box, message_label),
            fg_color="#030b16",
            hover_color="#102c40",
        )
        save_button.configure(text_color=GREEN)
        save_button.grid(row=4, column=0, padx=14, pady=(0, 14), sticky="e")
        title_entry.focus_set()

    def open_notes_window(self):
        self.show_view("notes")
        return
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
            fg_color="transparent",
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
        if hasattr(self, "notes_detail_frame") and self.notes_detail_frame.winfo_exists():
            self.show_note_detail(note)
            return

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
            border_color=LINE,
            corner_radius=RADIUS,
            font=ctk.CTkFont(size=11, weight="bold"),
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
            corner_radius=RADIUS,
            font=ctk.CTkFont(size=11, weight="bold"),
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
            if hasattr(self, "notes_detail_frame") and self.notes_detail_frame.winfo_exists():
                self.show_note_placeholder()
            self.set_status("Gotowy")
            return

        self.set_error_status("nie udało się usunąć notatki")
        self.after(1500, lambda: self.set_status("Gotowy"))

    def open_new_note_window(self):
        if hasattr(self, "notes_detail_frame") and self.notes_detail_frame.winfo_exists():
            self.show_new_note_form()
            return

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
            border_color=LINE,
            corner_radius=0,
            font=ctk.CTkFont(size=11, weight="bold"),
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
        self.show_view("settings")
        return
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
            corner_radius=0,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        close_button.grid(row=row + 1, column=1, padx=(6, 14), pady=(8, 14), sticky="ew")

    def build_settings_panel(self, parent):
        self.settings_panel = ctk.CTkFrame(
            parent,
            fg_color="transparent",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
        )
        self.settings_panel.grid(row=0, column=0, padx=14, pady=14, sticky="nsew")
        self.settings_panel.grid_columnconfigure(0, weight=1)
        self.settings_panel.grid_rowconfigure(1, weight=1)
        self.view_frames["settings"] = self.settings_panel

        ctk.CTkLabel(
            self.settings_panel,
            text="USTAWIENIA",
            text_color=CYAN,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
        ).grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")

        self.settings_content = ctk.CTkScrollableFrame(
            self.settings_panel,
            fg_color="#020713",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
            scrollbar_button_color=BLUE,
            scrollbar_button_hover_color=CYAN,
        )
        self.settings_content.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.settings_content.grid_columnconfigure(1, weight=1)
        self.settings_message_label = None
        self.settings_panel.grid_remove()

    def refresh_settings_view(self):
        if not hasattr(self, "settings_content"):
            return

        for widget in self.settings_content.winfo_children():
            widget.destroy()

        config_data, error = self.read_settings_config()
        values = config_data or {}

        settings_vars = {
            "voice_enabled": tk.BooleanVar(value=bool(values.get("voice_enabled", True))),
            "whisper_model": tk.StringVar(value=str(values.get("whisper_model", "base"))),
            "sample_rate": tk.StringVar(value=str(values.get("sample_rate", 48000))),
            "temperature": tk.StringVar(value=str(values.get("temperature", 0.3))),
            "edge_voice": tk.StringVar(value=str(values.get("edge_voice", "pl-PL-MarekNeural"))),
            "edge_rate": tk.StringVar(value=str(values.get("edge_rate", "+0%"))),
            "animation_speed": tk.StringVar(value=str(values.get("animation_speed", 1.6))),
            "backend_url": tk.StringVar(value=str(values.get("backend_url", "http://127.0.0.1:8000"))),
            "api_token": tk.StringVar(value=str(values.get("api_token", ""))),
            "text_scale": tk.StringVar(value=str(values.get("text_scale", self.text_scale))),
            "hud_scale": tk.StringVar(value=self.normalize_hud_scale(values.get("hud_scale", self.hud_scale))),
            "show_system_status": tk.BooleanVar(value=bool(values.get("show_system_status", self.show_system_status))),
        }
        self.settings_vars = settings_vars

        voice_checkbox = ctk.CTkCheckBox(
            self.settings_content,
            text="voice_enabled",
            variable=settings_vars["voice_enabled"],
            text_color=TEXT,
            fg_color=CYAN,
            hover_color=BLUE,
            border_color=LINE,
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
        )
        voice_checkbox.grid(row=0, column=0, columnspan=2, padx=14, pady=(14, 8), sticky="w")

        status_checkbox = ctk.CTkCheckBox(
            self.settings_content,
            text="Show System Status",
            variable=settings_vars["show_system_status"],
            command=lambda: self.preview_system_status_visibility(settings_vars["show_system_status"].get()),
            text_color=TEXT,
            fg_color=CYAN,
            hover_color=BLUE,
            border_color=LINE,
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
        )
        status_checkbox.grid(row=1, column=0, columnspan=2, padx=14, pady=(0, 10), sticky="w")

        row = 2
        self.add_settings_segmented(
            self.settings_content,
            row,
            "Text Scale",
            settings_vars["text_scale"],
            ["0.85", "1.0", "1.15", "1.3"],
        )
        row += 1
        self.add_settings_segmented(
            self.settings_content,
            row,
            "HUD Scale",
            settings_vars["hud_scale"],
            HUD_SCALE_OPTIONS,
        )
        row += 1

        for key, label in [
            ("backend_url", "Backend URL"),
        ]:
            self.add_settings_entry(self.settings_content, row, label, settings_vars[key])
            row += 1
        self.add_api_token_entry(self.settings_content, row, "API Token", settings_vars["api_token"])
        row += 1

        for key, label in [
            ("whisper_model", "whisper_model"),
            ("sample_rate", "sample_rate"),
            ("temperature", "temperature"),
            ("edge_voice", "edge_voice"),
            ("edge_rate", "edge_rate"),
            ("animation_speed", "animation_speed"),
        ]:
            self.add_settings_entry(self.settings_content, row, label, settings_vars[key])
            row += 1

        self.settings_message_label = ctk.CTkLabel(
            self.settings_content,
            text=f"Błąd config.json: {error}" if error else "",
            text_color=RED if error else GREEN_HOVER,
            wraplength=520,
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
        )
        self.settings_message_label.grid(row=row, column=0, columnspan=2, padx=14, pady=(8, 4), sticky="ew")

        save_button = self.create_action_button(
            self.settings_content,
            "ZAPISZ",
            lambda: self.save_settings(config_data, settings_vars, self.settings_message_label),
            fg_color="#030b16",
            hover_color="#102c40",
        )
        save_button.configure(text_color=GREEN)
        save_button.grid(row=row + 1, column=1, padx=(6, 14), pady=(8, 14), sticky="e")
        if config_data is None:
            save_button.configure(state="disabled")

    def add_settings_segmented(self, parent, row, label, variable, values):
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
        ).grid(row=row, column=0, padx=(14, 8), pady=7, sticky="ew")

        selector = ctk.CTkSegmentedButton(
            parent,
            values=values,
            variable=variable,
            height=26,
            selected_color="#08283a",
            selected_hover_color="#0c3348",
            unselected_color="#030b16",
            unselected_hover_color="#071827",
            text_color=TEXT,
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
            corner_radius=RADIUS,
        )
        selector.grid(row=row, column=1, padx=(0, 14), pady=7, sticky="ew")

    def preview_system_status_visibility(self, visible):
        self.show_system_status = bool(visible)
        self.apply_system_status_visibility()

    def add_settings_entry(self, parent, row, label, variable):
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
        ).grid(row=row, column=0, padx=(14, 8), pady=7, sticky="ew")

        entry = ctk.CTkEntry(
            parent,
            textvariable=variable,
            fg_color="#020713",
            text_color=TEXT,
            border_color=LINE,
            border_width=1,
            corner_radius=RADIUS,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        entry.grid(row=row, column=1, padx=(0, 14), pady=7, sticky="ew")

    def add_api_token_entry(self, parent, row, label, variable):
        ctk.CTkLabel(
            parent,
            text=label,
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
        ).grid(row=row, column=0, padx=(14, 8), pady=7, sticky="ew")

        token_frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        token_frame.grid(row=row, column=1, padx=(0, 14), pady=7, sticky="ew")
        token_frame.grid_columnconfigure(0, weight=1)

        self.api_token_visible = False
        self.api_token_entry = ctk.CTkEntry(
            token_frame,
            textvariable=variable,
            show="•",
            fg_color="#020713",
            text_color=TEXT,
            border_color=LINE,
            border_width=1,
            corner_radius=RADIUS,
            font=ctk.CTkFont(family="Consolas", size=11),
        )
        self.api_token_entry.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        self.api_token_toggle_button = ctk.CTkButton(
            token_frame,
            text="👁",
            command=self.toggle_api_token_visibility,
            width=30,
            height=28,
            fg_color="#030b16",
            hover_color="#15102b",
            text_color=MUTED,
            border_width=1,
            border_color=PURPLE,
            corner_radius=RADIUS,
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        )
        self.api_token_toggle_button.grid(row=0, column=1, sticky="e")

    def toggle_api_token_visibility(self):
        if not hasattr(self, "api_token_entry"):
            return
        self.api_token_visible = not getattr(self, "api_token_visible", False)
        self.api_token_entry.configure(show="" if self.api_token_visible else "•")
        if hasattr(self, "api_token_toggle_button"):
            self.api_token_toggle_button.configure(
                text="◌" if self.api_token_visible else "👁",
                text_color=CYAN if self.api_token_visible else MUTED,
                border_color=CYAN if self.api_token_visible else PURPLE,
            )

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
            updated_config["backend_url"] = settings_vars["backend_url"].get().strip() or "http://127.0.0.1:8000"
            updated_config["api_token"] = settings_vars["api_token"].get().strip()
            updated_config["animation_speed"] = self.clamp_animation_speed(
                float(settings_vars["animation_speed"].get().strip())
            )
            updated_config["text_scale"] = self.clamp_ui_scale(float(settings_vars["text_scale"].get().strip()))
            updated_config["hud_scale"] = float(self.normalize_hud_scale(settings_vars["hud_scale"].get().strip()))
            updated_config["show_system_status"] = bool(settings_vars["show_system_status"].get())
        except ValueError as e:
            message_label.configure(text=f"Błąd wartości: {e}", text_color="#ff3b5c")
            self.set_error_status(e)
            return

        try:
            with CONFIG_PATH.open("w", encoding="utf-8") as config_file:
                json.dump(updated_config, config_file, ensure_ascii=False, indent=2)
                config_file.write("\n")

            self.config = load_config()
            self.load_ui_preferences()
            self.apply_ui_preferences()
            self.update_system_status("Gotowy")
            self.refresh_lm_studio_status()
            message_label.configure(text="Zapisano ustawienia", text_color=GREEN_HOVER)
            self.append_history("Zapisano ustawienia")
            self.set_status("Gotowy")
        except Exception as e:
            message_label.configure(text=f"Błąd zapisu: {e}", text_color="#ff3b5c")
            self.set_error_status(e)

    def clamp_ui_scale(self, value):
        return max(0.75, min(1.45, float(value)))

    def normalize_hud_scale(self, value):
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return HUD_SCALE_OPTIONS[0]
        return min(HUD_SCALE_OPTIONS, key=lambda option: abs(float(option) - numeric_value))

    def load_ui_preferences(self):
        if not self.config:
            return
        self.text_scale = self.clamp_ui_scale(self.config.get("text_scale", 1.0))
        self.hud_scale = float(self.normalize_hud_scale(self.config.get("hud_scale", 1.15)))
        self.show_system_status = bool(self.config.get("show_system_status", True))

    def apply_ui_preferences(self):
        try:
            ctk.set_window_scaling(1.0)
            ctk.set_widget_scaling(self.hud_scale)
        except Exception:
            pass
        self.apply_text_scale()
        self.apply_hud_scale()
        self.apply_system_status_visibility()
        if hasattr(self, "core_canvas"):
            self.draw_core()

    def apply_hud_scale(self):
        if hasattr(self, "input_frame"):
            horizontal_pad = max(48, int(112 * self.hud_scale / 1.15))
            self.input_frame.grid_configure(padx=horizontal_pad)
        if hasattr(self, "entry"):
            self.entry.configure(height=max(38, int(42 * self.hud_scale / 1.15)))
        if hasattr(self, "listen_button"):
            size = max(38, int(42 * self.hud_scale / 1.15))
            self.listen_button.configure(width=size, height=size)
        if hasattr(self, "send_button"):
            self.send_button.configure(width=max(92, int(104 * self.hud_scale / 1.15)), height=max(38, int(42 * self.hud_scale / 1.15)))

    def build_apps_panel(self, parent):
        self.apps_panel = ctk.CTkFrame(
            parent,
            fg_color="transparent",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
        )
        self.apps_panel.grid(row=0, column=0, padx=14, pady=14, sticky="nsew")
        self.apps_panel.grid_columnconfigure(0, weight=1)
        self.apps_panel.grid_rowconfigure(1, weight=1)
        self.view_frames["apps"] = self.apps_panel

        header = ctk.CTkFrame(self.apps_panel, fg_color="transparent", corner_radius=0)
        header.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="APLIKACJE",
            text_color=CYAN,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
        ).grid(row=0, column=0, padx=0, pady=0, sticky="ew")

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

        self.apps_container = ctk.CTkScrollableFrame(
            self.apps_panel,
            fg_color="#020713",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
            scrollbar_button_color=BLUE,
            scrollbar_button_hover_color=CYAN,
        )
        self.apps_container.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")

        self.apps_panel.grid_remove()

    def toggle_apps_panel(self):
        self.show_view("apps")

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
                    if target == "whatsapp":
                        message = f"{self.assistant_name}: WhatsApp nie był uruchomiony."
                    else:
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
        self.content_frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        self.content_frame.grid(row=0, column=0, sticky="nsew")
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        core_frame = ctk.CTkFrame(self.content_frame, fg_color="transparent", corner_radius=0)
        core_frame.grid(row=0, column=0, padx=14, pady=14, sticky="nsew")
        core_frame.grid_columnconfigure(0, weight=1)
        core_frame.grid_rowconfigure(0, weight=1)
        core_frame.grid_rowconfigure(1, weight=0)
        self.view_frames["chat"] = core_frame

        self.core_canvas = tk.Canvas(
            core_frame,
            width=520,
            height=420,
            bg=BG,
            highlightthickness=0,
            bd=0,
        )
        self.core_canvas.grid(row=0, column=0, sticky="nsew")
        self.core_canvas.bind("<Configure>", self.draw_core)
        self.draw_core()

        self.core_state_label = ctk.CTkLabel(
            core_frame,
            text=self.core_state,
            text_color=GREEN,
            font=ctk.CTkFont(family="Consolas", size=12, weight="bold"),
        )
        self.build_apps_panel(self.content_frame)
        self.build_notes_panel(self.content_frame)
        self.build_settings_panel(self.content_frame)
        self.show_view("chat")

    def build_console_panel(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        tools = ctk.CTkFrame(parent, fg_color="transparent")
        tools.grid(row=0, column=0, padx=10, pady=(8, 6), sticky="ew")
        tools.grid_columnconfigure((0, 1), weight=1)

        self.control_pc_button = ctk.CTkButton(
            tools,
            text="Steruj PC",
            command=lambda: self.set_control_mode("Steruj PC"),
            height=24,
            fg_color="#120d22",
            hover_color="#201438",
            text_color=TEXT,
            border_width=1,
            border_color=PURPLE,
            corner_radius=RADIUS,
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
        )
        self.control_pc_button.grid(row=0, column=0, padx=(0, 5), sticky="ew")

        self.control_phone_button = ctk.CTkButton(
            tools,
            text="Steruj telefonem",
            command=lambda: self.set_control_mode("Steruj telefonem"),
            height=24,
            fg_color="#030b16",
            hover_color="#201438",
            text_color=MUTED,
            border_width=1,
            border_color=PURPLE,
            corner_radius=RADIUS,
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
        )
        self.control_phone_button.grid(row=0, column=1, padx=(5, 0), sticky="ew")

        log_header = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        log_header.grid(row=1, column=0, padx=10, pady=(0, 6), sticky="new")
        log_header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_header,
            text="CONSOLE LOG",
            text_color=CYAN,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self.log_clear_button = ctk.CTkButton(
            log_header,
            text="Clear",
            command=self.clear_history,
            width=56,
            height=20,
            fg_color="#030b16",
            hover_color="#102c40",
            text_color=MUTED,
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
            font=ctk.CTkFont(family="Consolas", size=8, weight="bold"),
        )
        self.log_clear_button.grid(row=0, column=1, sticky="e")

        self.history = ctk.CTkTextbox(
            parent,
            wrap="word",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color=TEXT,
            fg_color="#020713",
            border_width=1,
            border_color=LINE,
            corner_radius=RADIUS,
        )
        self.history.grid(row=1, column=0, padx=10, pady=(26, 10), sticky="nsew")
        self.history.configure(state="disabled")
        self.update_control_mode_buttons()

    def build_system_status(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            parent,
            text="SYSTEM STATUS",
            text_color=CYAN,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
        ).grid(row=0, column=0, padx=10, pady=(10, 8), sticky="ew")

        clock_frame = ctk.CTkFrame(
            parent,
            fg_color="transparent",
            border_width=1,
            border_color=LINE,
            corner_radius=0,
        )
        clock_frame.grid(row=1, column=0, padx=10, pady=(0, 8), sticky="ew")
        clock_frame.grid_columnconfigure(0, weight=1)

        self.time_label = ctk.CTkLabel(
            clock_frame,
            text="--:--:--",
            text_color=CYAN,
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
        )
        self.time_label.grid(row=0, column=0, padx=8, pady=(6, 0), sticky="ew")

        self.date_label = ctk.CTkLabel(
            clock_frame,
            text="---- -- --",
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=9),
        )
        self.date_label.grid(row=1, column=0, padx=8, pady=(0, 6), sticky="ew")

        self.add_status_row(parent, 2, "Backend", "Online")
        self.add_status_row(parent, 3, "Hub", "Offline")
        self.lm_server_label = self.add_status_row(parent, 4, "Processor / LLM", "Offline")
        self.add_status_row(parent, 5, "Agent PC", "Offline")
        self.phone_status_label = self.add_status_row(parent, 6, "Telefon", "Offline")
        self.add_status_row(parent, 7, "Tryb", "PC")
        self.lm_model_label = self.add_status_row(parent, 8, "Model", "brak")
        self.add_status_row(parent, 9, "Device ID", "local-pc")
        self.add_status_row(parent, 10, "API Token", "brak")
        self.add_status_row(parent, 11, "Mikrofon", "Nieznany")

        ctk.CTkLabel(
            parent,
            text="LOCAL NODE ACTIVE",
            text_color=MUTED,
            font=ctk.CTkFont(family="Consolas", size=8),
        ).grid(row=12, column=0, padx=10, pady=(14, 0), sticky="s")

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
        frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        frame.grid(row=row, column=0, padx=10, pady=0, sticky="ew")
        frame.grid_columnconfigure(0, weight=0, minsize=92)
        frame.grid_columnconfigure(1, weight=0)
        frame.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            frame,
            text=name.upper(),
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=8, weight="bold"),
        ).grid(row=0, column=0, padx=(0, 6), pady=4, sticky="w")

        dot_color = GREEN if str(value).lower() not in {"offline", "brak", "brak danych", "nieznany"} else RED
        dot_label = ctk.CTkLabel(
            frame,
            text="●",
            text_color=dot_color,
            font=ctk.CTkFont(family="Consolas", size=7, weight="bold"),
        )
        dot_label.grid(row=0, column=1, padx=(0, 5), pady=4, sticky="e")

        value_label = ctk.CTkLabel(
            frame,
            text=value,
            text_color=TEXT,
            anchor="e",
            font=ctk.CTkFont(family="Consolas", size=8),
        )
        value_label.grid(row=0, column=2, padx=(0, 0), pady=4, sticky="ew")
        self.system_labels[name] = value_label
        self.status_dots[name] = dot_label
        return value_label

    def add_status_row(self, parent, row, name, value):
        frame = ctk.CTkFrame(parent, fg_color="transparent", corner_radius=0)
        frame.grid(row=row, column=0, padx=10, pady=0, sticky="ew")
        frame.grid_columnconfigure(0, weight=0, minsize=92)
        frame.grid_columnconfigure(1, weight=0)
        frame.grid_columnconfigure(2, weight=1)

        ctk.CTkLabel(
            frame,
            text=name.upper(),
            text_color=MUTED,
            anchor="w",
            font=ctk.CTkFont(family="Consolas", size=8, weight="bold"),
        ).grid(row=0, column=0, padx=(0, 6), pady=4, sticky="w")

        dot_color = GREEN if str(value).lower() not in {"offline", "brak", "brak danych", "nieznany"} else RED
        dot_label = ctk.CTkLabel(
            frame,
            text="\u25cf",
            text_color=dot_color,
            font=ctk.CTkFont(family="Consolas", size=7, weight="bold"),
        )
        dot_label.grid(row=0, column=1, padx=(0, 5), pady=4, sticky="e")

        value_label = ctk.CTkLabel(
            frame,
            text=value,
            text_color=TEXT,
            anchor="e",
            font=ctk.CTkFont(family="Consolas", size=8),
        )
        value_label.grid(row=0, column=2, pady=4, sticky="ew")
        self.system_labels[name] = value_label
        self.status_dots[name] = dot_label
        return value_label

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

        width = max(canvas.winfo_width(), 360)
        height = max(canvas.winfo_height(), 320)
        self.draw_hud_grid(canvas, width, height)
        cx = width / 2
        cy = height / 2
        pulse = 1 + math.sin(self.pulse_phase / 14) * 0.025
        radius = min(76, max(46, min(width, height) * 0.09 * self.hud_scale)) * pulse

        for scale, color, line_width in [
            (1.0, LINE, 1),
            (0.76, "#15384c", 1),
            (0.48, CYAN, 1),
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

        sweep = math.radians((self.pulse_phase * 2.1) % 360)
        canvas.create_line(
            cx,
            cy,
            cx + math.cos(sweep) * radius * 0.9,
            cy + math.sin(sweep) * radius * 0.9,
            fill=self.fade_color(CYAN, progress),
            width=1,
        )

        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            inner = radius * 0.88
            outer = radius * 1.02
            x1 = cx + math.cos(radians) * inner
            y1 = cy + math.sin(radians) * inner
            x2 = cx + math.cos(radians) * outer
            y2 = cy + math.sin(radians) * outer
            canvas.create_line(x1, y1, x2, y2, fill=self.fade_color(LINE, progress), width=1)

        dot_x = cx + math.cos(sweep + 0.7) * radius * 0.55
        dot_y = cy + math.sin(sweep + 0.7) * radius * 0.55
        canvas.create_oval(dot_x - 2, dot_y - 2, dot_x + 2, dot_y + 2, fill=self.fade_color(GREEN, progress), outline="")
        canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill=self.fade_color(CYAN, progress), outline="")

        canvas.create_text(cx, cy + radius + 22, text=self.core_state, fill=self.fade_color(GREEN, progress), font=("Consolas", 9, "bold"))

    def draw_hud_grid(self, canvas, width, height):
        for x in range(0, int(width), 42):
            canvas.create_line(x, 0, x, height, fill="#041321", width=1)
        for y in range(0, int(height), 42):
            canvas.create_line(0, y, width, y, fill="#041321", width=1)
        for x in range(21, int(width), 42):
            for y in range(21, int(height), 42):
                canvas.create_oval(x - 1, y - 1, x + 1, y + 1, fill="#092034", outline="")

    def draw_root_grid(self, _event=None):
        if not hasattr(self, "bg_canvas"):
            return
        canvas = self.bg_canvas
        canvas.delete("all")
        width = max(canvas.winfo_width(), 1)
        height = max(canvas.winfo_height(), 1)
        for x in range(0, int(width), 44):
            canvas.create_line(x, 0, x, height, fill="#03111d", width=1)
        for y in range(0, int(height), 44):
            canvas.create_line(0, y, width, y, fill="#03111d", width=1)
        for x in range(22, int(width), 44):
            for y in range(22, int(height), 44):
                canvas.create_oval(x - 1, y - 1, x + 1, y + 1, fill="#061a2a", outline="")

    def draw_wave_frame(self, progress, motion_phase):
        progress = self.clamp(progress)
        speed = self.get_animation_speed()
        canvas = self.core_canvas
        canvas.delete("all")

        width = max(canvas.winfo_width(), 360)
        height = max(canvas.winfo_height(), 320)
        self.draw_hud_grid(canvas, width, height)
        cx = width / 2
        cy = height / 2
        palette = [CYAN, BLUE, PURPLE, "#495f83"]

        frame_color = self.fade_color(LINE, progress)
        canvas.create_line(width * 0.38, cy - 78, width * 0.62, cy - 78, fill=frame_color, width=1)
        canvas.create_line(width * 0.38, cy + 78, width * 0.62, cy + 78, fill=frame_color, width=1)

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
            bar_height = (5 + height_scale * 64) * progress * edge_envelope
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

        canvas.create_text(cx, cy - 112, text="LISTENING", fill=self.fade_color(GREEN, progress), font=("Consolas", 10, "bold"))
        canvas.create_text(
            cx,
            cy + 112,
            text="AUDIO INPUT ACTIVE",
            fill=self.fade_color(MUTED, progress),
            font=("Consolas", 8, "bold"),
        )

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
            self.load_ui_preferences()
            self.apply_ui_preferences()
            self.assistant_name = self.config["assistant_name"]
            self.client = create_client(self.config)
            self.messages = create_messages(self.config)
            self.update_system_status("Gotowy")
            self.refresh_lm_studio_status()
            self.refresh_hub_agent_status()
            self.refresh_phone_status()
            self.after(5000, self.refresh_phone_status_periodic)
            self.after(5000, self.refresh_hub_agent_status_periodic)
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

        extra_values = {
            "Tryb głosu": "Włączony" if self.config.get("voice_enabled", False) else "Wyłączony",
            "Model": self.config.get("model", "local-model"),
            "Device ID": self.config.get("device_id", "local-pc"),
            "API Token": "••••••" if self.config.get("api_token") else "brak",
        }
        for name, value in extra_values.items():
            label = self.system_labels.get(name)
            if label:
                label.configure(text=str(value))

    def refresh_lm_studio_status(self):
        if self.lm_server_label:
            self.lm_server_label.configure(text="Sprawdzam...")
        if self.lm_model_label:
            self.lm_model_label.configure(text="Sprawdzam...")

        thread = threading.Thread(target=self.refresh_lm_studio_status_worker, daemon=True)
        thread.start()

    def refresh_lm_studio_status_worker(self):
        expected_model = "local-model"
        if self.config:
            expected_model = self.config.get("model", expected_model)

        server_text = "Offline"
        model_text = "brak"

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

            server_text = "Online"
            if expected_model in model_ids:
                model_text = f"{expected_model}"
        except Exception:
            pass

        self.after(0, lambda: self.update_lm_studio_labels(server_text, model_text))

    def update_lm_studio_labels(self, server_text, model_text):
        if self.lm_server_label:
            self.lm_server_label.configure(text=server_text)
        dot = self.status_dots.get("Processor / LLM")
        if dot:
            dot.configure(text_color=GREEN if server_text == "Online" else RED)
        if self.lm_model_label:
            self.lm_model_label.configure(text=model_text)
        model_dot = self.status_dots.get("Model")
        if model_dot:
            model_dot.configure(text_color=GREEN if model_text != "brak" else RED)

    def refresh_phone_status(self):
        if self.phone_status_label:
            self.phone_status_label.configure(text="Sprawdzam...")

        thread = threading.Thread(target=self.refresh_phone_status_worker, daemon=True)
        thread.start()

    def refresh_phone_status_periodic(self):
        self.refresh_phone_status()
        self.after(5000, self.refresh_phone_status_periodic)

    def refresh_hub_agent_status(self):
        thread = threading.Thread(target=self.refresh_hub_agent_status_worker, daemon=True)
        thread.start()

    def refresh_hub_agent_status_periodic(self):
        self.refresh_hub_agent_status()
        self.after(5000, self.refresh_hub_agent_status_periodic)

    def refresh_hub_agent_status_worker(self):
        hub_status = "Offline"
        agent_status = "Offline"

        try:
            if requests is None:
                raise RuntimeError("requests is not installed")

            hub_url = "http://127.0.0.1:8002"
            auth_token = "dev-token"
            device_id = "local-pc"
            if self.config:
                hub_url = str(self.config.get("hub_url") or hub_url).replace("ws://", "http://").replace("wss://", "https://").rstrip("/")
                auth_token = str(self.config.get("auth_token") or auth_token)
                device_id = str(self.config.get("device_id") or device_id)

            health_response = requests.get(f"{hub_url}/health", timeout=1.5)
            health_response.raise_for_status()
            hub_status = "Online"

            agents_response = requests.get(
                f"{hub_url}/agents",
                headers={"X-Jarvis-Token": auth_token},
                timeout=1.5,
            )
            agents_response.raise_for_status()
            agents = agents_response.json().get("agents", [])
            if device_id in agents:
                agent_status = "Online"
        except Exception:
            pass

        self.after(0, lambda: self.update_hub_agent_labels(hub_status, agent_status))

    def update_hub_agent_labels(self, hub_status, agent_status):
        hub_label = self.system_labels.get("Hub")
        if hub_label:
            hub_label.configure(text=hub_status)
        hub_dot = self.status_dots.get("Hub")
        if hub_dot:
            hub_dot.configure(text_color=GREEN if hub_status == "Online" else RED)
        agent_label = self.system_labels.get("Agent PC")
        if agent_label:
            agent_label.configure(text=agent_status)
        agent_dot = self.status_dots.get("Agent PC")
        if agent_dot:
            agent_dot.configure(text_color=GREEN if agent_status == "Online" else RED)

    def refresh_phone_status_worker(self):
        status_text = "Offline"
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
            backend_url = str(self.config.get("backend_url") or "http://127.0.0.1:8000").rstrip("/")

            response = requests.get(
                f"{backend_url}/phone/status",
                headers={"X-Jarvis-Token": token},
                timeout=2,
            )
            if response.status_code == 401:
                raise RuntimeError("token API odrzucony")
            response.raise_for_status()

            data = response.json()
            status_text = "Online" if data.get("online") else "Offline"
            seen_text = f"Ostatnio widziany: {data.get('last_seen') or 'brak'}"
            command_text = f"Ostatnia komenda: {data.get('last_command') or 'brak'}"
        except Exception as e:
            status_text = "Błąd"
            seen_text = "Ostatnio widziany: brak"
            command_text = f"Ostatnia komenda: {str(e).splitlines()[0][:32]}"

        self.after(
            0,
            lambda: self.update_phone_status_labels(status_text, seen_text, command_text),
        )

    def update_phone_status_labels(self, status_text, seen_text, command_text):
        if self.phone_status_label:
            self.phone_status_label.configure(text=status_text)
        phone_dot = self.status_dots.get("Telefon")
        if phone_dot:
            phone_dot.configure(text_color=GREEN if status_text == "Online" else RED)
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
        self.update_control_mode_buttons()
        mode_label = self.system_labels.get("Tryb")
        if mode_label:
            mode_label.configure(text="Telefon" if self.is_phone_control_mode() else "PC")
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

    def update_control_mode_buttons(self):
        if not hasattr(self, "control_pc_button") or not hasattr(self, "control_phone_button"):
            return
        pc_active = not self.is_phone_control_mode()
        self.control_pc_button.configure(
            fg_color="#17102a" if pc_active else "#030b16",
            text_color=TEXT if pc_active else MUTED,
            border_color="#a58cff" if pc_active else PURPLE,
        )
        self.control_phone_button.configure(
            fg_color="#17102a" if not pc_active else "#030b16",
            text_color=TEXT if not pc_active else MUTED,
            border_color="#a58cff" if not pc_active else PURPLE,
        )

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
        backend_url = str(self.config.get("backend_url") or "http://127.0.0.1:8000").rstrip("/")

        response = requests.post(
            f"{backend_url}/phone/command",
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
        normalized = str(status).lower()
        if "słuch" in normalized or "sĹ‚uch" in normalized:
            self.core_state = "LISTENING"
        elif "rozpozn" in normalized or "my" in normalized or "wykon" in normalized:
            self.core_state = "PROCESSING"
        elif "błąd" in normalized or "bĹ‚Ä…d" in normalized:
            self.core_state = "ERROR"
        elif "mówi" in normalized or "odpow" in normalized:
            self.core_state = "RESPONDING"
        else:
            self.core_state = "READY"
        if hasattr(self, "core_state_label"):
            color = RED if self.core_state == "ERROR" else GREEN
            self.core_state_label.configure(text=self.core_state, text_color=color)

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

    def show_entry_placeholder(self):
        if not hasattr(self, "entry"):
            return
        self.entry_placeholder_active = True
        self.entry.configure(text_color=PLACEHOLDER)
        self.entry.delete("1.0", "end")
        self.entry.insert("1.0", self.entry_placeholder)

    def hide_entry_placeholder(self):
        if self.entry_placeholder_active:
            self.entry.delete("1.0", "end")
            self.entry.configure(text_color=TEXT)
            self.entry_placeholder_active = False

    def on_entry_focus_in(self, _event):
        self.hide_entry_placeholder()

    def on_entry_focus_out(self, _event):
        if not self.entry.get("1.0", "end-1c").strip():
            self.show_entry_placeholder()

    def on_entry_key_press(self, event):
        if self.entry_placeholder_active and event.keysym not in {"Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "Tab"}:
            self.hide_entry_placeholder()

    def on_entry_return(self, event):
        self.hide_entry_placeholder()
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

        if self.entry_placeholder_active:
            return

        user_text = self.entry.get("1.0", "end-1c").strip()
        if not user_text:
            return

        self.entry.delete("1.0", "end")
        self.show_entry_placeholder()
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
                self.set_status_from_thread("Odpowiadam")
                from voice import speak

                speak(text)
                self.after(0, lambda: self.set_status("Gotowy"))
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
