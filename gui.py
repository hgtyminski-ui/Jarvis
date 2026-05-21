import contextlib
import datetime
import io
import math
import sys
import threading
import tkinter as tk

import customtkinter as ctk

from actions import parse_ai_json, parse_local_action
from ai_client import create_client
from config import ConfigError, load_config
from memory import add_assistant_message, add_user_message, create_messages
from text_utils import normalize_text

try:
    import psutil
except ImportError:
    psutil = None


BG = "#05070b"
PANEL = "#0b111a"
PANEL_2 = "#08131d"
CYAN = "#00d9ff"
BLUE = "#1b70ff"
TEXT = "#d9f7ff"
MUTED = "#6f95a3"
LINE = "#0c5a78"


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
        self.pulse_phase = 0
        self.system_labels = {}

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
        self.status_label.grid(row=1, column=0, sticky="ew")

        self.close_button = ctk.CTkButton(
            header,
            text="X",
            command=self.close_window,
            width=34,
            height=28,
            fg_color="#17080d",
            hover_color="#42101a",
            text_color="#ff5c7a",
            border_width=1,
            border_color=CYAN,
            corner_radius=6,
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.close_button.grid(row=0, column=1, padx=(12, 0), pady=(4, 0), sticky="ne")

        ctk.CTkFrame(header, fg_color=CYAN, height=1, corner_radius=0).grid(
            row=2,
            column=0,
            columnspan=2,
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
        self.build_quick_actions(self.left_panel)

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
            fg_color="#050b12",
            border_width=1,
            border_color="#14384a",
            corner_radius=8,
        )
        self.entry.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=10, sticky="ew")
        self.entry.bind("<Return>", self.on_entry_return)
        self.entry.bind("<Shift-Return>", self.on_entry_shift_return)

        self.send_button = self.create_action_button(
            self.input_frame,
            "Wyślij",
            self.send_text,
            fg_color=BLUE,
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
            fg_color="#15202b",
            hover_color="#203244",
        )
        self.clear_button.grid(row=1, column=1, columnspan=2, padx=(0, 10), pady=(0, 10), sticky="ew")

    def create_panel(self, parent):
        return ctk.CTkFrame(
            parent,
            fg_color=PANEL,
            border_width=1,
            border_color="#123348",
            corner_radius=8,
        )

    def create_action_button(self, parent, text, command, fg_color="#0d2f45", hover_color="#124f70"):
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

    def build_quick_actions(self, parent):
        parent.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            parent,
            text="SZYBKIE AKCJE",
            text_color=CYAN,
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, padx=14, pady=(16, 10), sticky="ew")

        actions = [
            ("Spotify", "otwórz spotify"),
            ("YouTube", "otwórz youtube"),
            ("Steam", "otwórz steam"),
            ("Discord", "otwórz discord"),
            ("VS Code", "otwórz vscode"),
            ("Netflix", "otwórz netflix"),
        ]

        for row, (label, command) in enumerate(actions, start=1):
            button = self.create_action_button(
                parent,
                label,
                lambda command=command: self.run_quick_action(command),
            )
            button.grid(row=row, column=0, padx=14, pady=5, sticky="ew")

        ctk.CTkLabel(
            parent,
            text="LOCAL COMMAND GRID",
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
        ).grid(row=8, column=0, padx=14, pady=(18, 0), sticky="s")

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
            fg_color="#03070c",
            border_width=1,
            border_color="#14384a",
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
            fg_color="#07101a",
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

        self.add_status_row(parent, 2, "LM Studio", "Nieznany")
        self.add_status_row(parent, 3, "Model", "Nieznany")
        self.add_status_row(parent, 4, "Tryb głosu", "Nieznany")
        self.add_status_row(parent, 5, "Mikrofon", "Nieznany")
        self.add_status_row(parent, 6, "CPU", "brak danych")
        self.add_status_row(parent, 7, "RAM", "brak danych")

        ctk.CTkLabel(
            parent,
            text="HUD LINK ACTIVE",
            text_color=MUTED,
            font=ctk.CTkFont(size=11),
        ).grid(row=8, column=0, padx=14, pady=(18, 0), sticky="s")

    def add_status_row(self, parent, row, name, value):
        frame = ctk.CTkFrame(parent, fg_color="#07101a", corner_radius=6)
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
        canvas = self.core_canvas
        canvas.delete("all")

        width = max(canvas.winfo_width(), 420)
        height = max(canvas.winfo_height(), 285)
        cx = width / 2
        cy = height / 2
        pulse = 1 + math.sin(self.pulse_phase / 10) * 0.05
        radius = min(width, height) * 0.36 * pulse

        canvas.create_line(22, 28, width * 0.28, 28, fill=LINE, width=1)
        canvas.create_line(width * 0.72, 28, width - 22, 28, fill=LINE, width=1)
        canvas.create_line(22, height - 28, width * 0.28, height - 28, fill=LINE, width=1)
        canvas.create_line(width * 0.72, height - 28, width - 22, height - 28, fill=LINE, width=1)

        for scale, color, line_width in [
            (1.18, "#06445c", 1),
            (1.0, CYAN, 2),
            (0.82, "#18a8ff", 1),
            (0.62, BLUE, 2),
            (0.42, "#79efff", 1),
            (0.23, "#d6fbff", 1),
        ]:
            r = radius * scale
            canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=line_width)

        for angle in range(0, 360, 30):
            radians = math.radians(angle + self.pulse_phase * 1.4)
            inner = radius * 1.02
            outer = radius * 1.22
            x1 = cx + math.cos(radians) * inner
            y1 = cy + math.sin(radians) * inner
            x2 = cx + math.cos(radians) * outer
            y2 = cy + math.sin(radians) * outer
            canvas.create_line(x1, y1, x2, y2, fill=CYAN, width=1)

        for angle in range(0, 360, 90):
            radians = math.radians(angle - self.pulse_phase)
            arc_radius = radius * 0.72
            x = cx + math.cos(radians) * arc_radius
            y = cy + math.sin(radians) * arc_radius
            canvas.create_oval(x - 3, y - 3, x + 3, y + 3, fill=CYAN, outline="")

        canvas.create_text(cx, cy - 10, text="CORE", fill=TEXT, font=("Segoe UI", 24, "bold"))
        canvas.create_text(cx, cy + 22, text="ONLINE", fill=CYAN, font=("Segoe UI", 14, "bold"))
        canvas.create_line(26, height - 24, width - 26, height - 24, fill="#0e4c67", width=1)
        canvas.create_text(width - 58, height - 40, text="PULSE", fill=MUTED, font=("Consolas", 10))

    def animate_core(self):
        self.pulse_phase = (self.pulse_phase + 1) % 360
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
            self.append_history(f"{self.assistant_name} uruchomiony.")
        except ConfigError as e:
            self.update_system_status("Błąd")
            self.append_history(f"Błąd konfiguracji: {e}")
            self.set_controls_enabled(False)
        except Exception as e:
            self.update_system_status("Błąd")
            self.append_history(f"Błąd uruchamiania GUI: {e}")
            self.set_controls_enabled(False)

    def update_system_status(self, lm_status=None):
        if not self.config:
            label = self.system_labels.get("LM Studio")
            if label and lm_status:
                label.configure(text=str(lm_status))
            return

        values = {
            "LM Studio": lm_status or "Skonfigurowany",
            "Model": self.config.get("model", "Nieznany"),
            "Tryb głosu": "Włączony" if self.config.get("voice_enabled", False) else "Wyłączony",
            "Mikrofon": f"Urządzenie {self.config.get('microphone_device', 'auto')}",
        }

        for name, value in values.items():
            label = self.system_labels.get(name)
            if label:
                label.configure(text=str(value))

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

    def set_status(self, status):
        clean_status = status.replace("...", "")
        self.status_label.configure(text=clean_status)

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

    def run_quick_action(self, command):
        if self.is_busy:
            return

        self.submit_user_text(command)

    def submit_user_text(self, user_text):
        if user_text.lower() == "/listen":
            self.append_history("Przytrzymaj przycisk Listen, aby nagrywać.")
            return

        self.append_history(f"Ty: {user_text}")
        self.set_controls_enabled(False)

        status = "Wykonuję" if self.is_local_action(user_text) else "Myślę"
        self.set_status(status)

        thread = threading.Thread(target=self.run_text_worker, args=(user_text,), daemon=True)
        thread.start()

    def is_local_action(self, text):
        if text.startswith("/"):
            return True

        return parse_local_action(text) is not None

    def run_text_worker(self, user_text):
        try:
            should_exit, output, tts_text = self.process_user_text_for_gui(user_text)
            self.append_from_thread(output)
            self.speak_in_background(tts_text)

            if should_exit:
                self.after(300, self.destroy)
                return
        except Exception as e:
            self.append_from_thread(f"Błąd: {e}")
        finally:
            self.after(0, self.finish_work)

    def on_listen_press(self, _event):
        if self.is_busy:
            return

        self.is_busy = True
        self.is_recording = True
        self.set_text_controls_enabled(False)
        self.set_status("Słucham")

        try:
            from speech_input import start_recording

            started, output = self.capture_output(start_recording)
            self.append_history(output)

            if not started:
                self.is_recording = False
                self.finish_work()
        except Exception as e:
            self.append_history(f"Błąd: {e}")
            self.is_recording = False
            self.finish_work()

    def on_listen_release(self, _event):
        if not self.is_recording:
            return

        self.is_recording = False
        self.listen_button.configure(state="disabled")
        self.set_status("Myślę")

        thread = threading.Thread(target=self.listen_release_worker, daemon=True)
        thread.start()

    def listen_release_worker(self):
        try:
            from speech_input import stop_recording_and_transcribe

            spoken_text, listen_output = self.capture_output(stop_recording_and_transcribe)
            self.append_from_thread(listen_output)

            if not spoken_text:
                return

            self.append_from_thread(f"Ty: {spoken_text}")
            status = "Wykonuję" if self.is_local_action(spoken_text) else "Myślę"
            self.set_status_from_thread(status)

            _should_exit, output, tts_text = self.process_user_text_for_gui(spoken_text)
            self.append_from_thread(output)
            self.speak_in_background(tts_text)
        except Exception as e:
            self.append_from_thread(f"Błąd: {e}")
        finally:
            self.after(0, self.finish_work)

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
        normalized_exit_commands = [
            normalize_text(command) for command in self.config["exit_commands"]
        ]

        if normalized_user_input in normalized_exit_commands:
            return True, f"{self.assistant_name}: Wyłączam się. Do zobaczenia!", None

        local_action = parse_local_action(user_input)
        if local_action:
            import json
            from main import handle_ai_answer

            _result, output = self.capture_output(
                lambda: handle_ai_answer(
                    json.dumps(local_action),
                    self.assistant_name,
                    self.config,
                )
            )
            return False, output, None

        add_user_message(self.messages, normalized_user_input)

        try:
            from ai_client import get_ai_response

            answer = get_ai_response(self.client, self.messages, self.config)
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

        from main import handle_ai_answer

        _result, output = self.capture_output(
            lambda: handle_ai_answer(answer, self.assistant_name, self.config)
        )
        return output, None

    def speak_in_background(self, text):
        if not text or not self.config.get("voice_enabled", False):
            return

        def worker():
            try:
                from voice import speak

                speak(text)
            except Exception as e:
                try:
                    print("Błąd TTS:", e, file=sys.__stderr__ or sys.stderr)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = JarvisGUI()
    app.mainloop()
