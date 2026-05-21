import contextlib
import io
import threading

import customtkinter as ctk

from actions import parse_ai_json, parse_local_action
from ai_client import create_client
from config import ConfigError, load_config
from memory import add_assistant_message, add_user_message, create_messages
from text_utils import normalize_text


class JarvisGUI(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        super().__init__()

        self.title("Jarvis")
        self.geometry("900x650")
        self.minsize(720, 500)

        self.assistant_name = "Jarvis"
        self.client = None
        self.config = None
        self.messages = None
        self.is_busy = False
        self.is_recording = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.status_label = ctk.CTkLabel(
            self,
            text="Status: Gotowy",
            anchor="w",
            font=ctk.CTkFont(size=15, weight="bold"),
        )
        self.status_label.grid(row=0, column=0, padx=16, pady=(14, 8), sticky="ew")

        self.history = ctk.CTkTextbox(
            self,
            wrap="word",
            font=ctk.CTkFont(size=15),
            border_width=1,
            corner_radius=8,
        )
        self.history.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="nsew")
        self.history.configure(state="disabled")

        self.input_frame = ctk.CTkFrame(self, corner_radius=8)
        self.input_frame.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="ew")
        self.input_frame.grid_columnconfigure(0, weight=1)

        self.entry = ctk.CTkTextbox(
            self.input_frame,
            height=96,
            wrap="word",
            font=ctk.CTkFont(size=14),
            border_width=1,
            corner_radius=8,
        )
        self.entry.grid(row=0, column=0, rowspan=2, padx=(10, 8), pady=10, sticky="ew")
        self.entry.bind("<Return>", self.on_entry_return)
        self.entry.bind("<Shift-Return>", self.on_entry_shift_return)

        self.send_button = ctk.CTkButton(
            self.input_frame,
            text="Wyślij",
            command=self.send_text,
            width=110,
        )
        self.send_button.grid(row=0, column=1, padx=(0, 10), pady=(10, 6), sticky="ew")

        self.listen_button = ctk.CTkButton(self.input_frame, text="Listen", width=110)
        self.listen_button.grid(row=0, column=2, padx=(0, 10), pady=(10, 6), sticky="ew")
        self.listen_button.bind("<ButtonPress-1>", self.on_listen_press)
        self.listen_button.bind("<ButtonRelease-1>", self.on_listen_release)

        self.clear_button = ctk.CTkButton(
            self.input_frame,
            text="Wyczyść",
            command=self.clear_history,
            width=110,
            fg_color="#3a3a3a",
            hover_color="#4a4a4a",
        )
        self.clear_button.grid(row=1, column=1, columnspan=2, padx=(0, 10), pady=(0, 10), sticky="ew")

        self.load_jarvis()

    def load_jarvis(self):
        try:
            self.config = load_config()
            self.assistant_name = self.config["assistant_name"]
            self.client = create_client(self.config)
            self.messages = create_messages(self.config)
            self.append_history(f"{self.assistant_name} uruchomiony.")
        except ConfigError as e:
            self.append_history(f"Błąd konfiguracji: {e}")
            self.set_controls_enabled(False)
        except Exception as e:
            self.append_history(f"Błąd uruchamiania GUI: {e}")
            self.set_controls_enabled(False)

    def set_status(self, status):
        self.status_label.configure(text=f"Status: {status}")

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

        self.history.configure(state="normal")
        self.history.insert("end", text.rstrip() + "\n")
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
        from actions import parse_local_action

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
        self.set_status("Słucham...")

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
        self.set_status("Rozpoznaję...")

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
                import sys

                try:
                    print("Błąd TTS:", e, file=sys.__stderr__ or sys.stderr)
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = JarvisGUI()
    app.mainloop()
