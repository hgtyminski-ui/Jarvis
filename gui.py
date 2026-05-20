import contextlib
import io
import threading

import customtkinter as ctk

from ai_client import create_client
from config import ConfigError, load_config
from main import process_user_text
from memory import create_messages


class JarvisGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Jarvis")
        self.geometry("760x520")
        self.minsize(560, 380)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.assistant_name = "Jarvis"
        self.client = None
        self.config = None
        self.messages = None
        self.is_busy = False
        self.is_recording = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.history = ctk.CTkTextbox(self, wrap="word")
        self.history.grid(row=0, column=0, columnspan=3, padx=12, pady=(12, 8), sticky="nsew")
        self.history.configure(state="disabled")

        self.entry = ctk.CTkEntry(self, placeholder_text="Napisz do Jarvisa...")
        self.entry.grid(row=1, column=0, padx=(12, 8), pady=(0, 8), sticky="ew")
        self.entry.bind("<Return>", lambda _event: self.send_text())

        self.send_button = ctk.CTkButton(self, text="Wyślij", command=self.send_text)
        self.send_button.grid(row=1, column=1, padx=(0, 8), pady=(0, 8))

        self.listen_button = ctk.CTkButton(self, text="Listen")
        self.listen_button.grid(row=1, column=2, padx=(0, 12), pady=(0, 8))
        self.listen_button.bind("<ButtonPress-1>", self.on_listen_press)
        self.listen_button.bind("<ButtonRelease-1>", self.on_listen_release)

        self.status_label = ctk.CTkLabel(self, text="Status: Gotowy", anchor="w")
        self.status_label.grid(row=2, column=0, columnspan=3, padx=12, pady=(0, 12), sticky="ew")

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

    def append_history(self, text):
        if not text:
            return

        self.history.configure(state="normal")
        self.history.insert("end", text.rstrip() + "\n")
        self.history.see("end")
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

        user_text = self.entry.get().strip()
        if not user_text:
            return

        self.entry.delete(0, "end")

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
            should_exit, output = self.capture_output(
                lambda: process_user_text(
                    user_text,
                    self.assistant_name,
                    self.client,
                    self.config,
                    self.messages,
                )
            )
            self.append_from_thread(output)

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

            _should_exit, output = self.capture_output(
                lambda: process_user_text(
                    spoken_text,
                    self.assistant_name,
                    self.client,
                    self.config,
                    self.messages,
                )
            )
            self.append_from_thread(output)
        except Exception as e:
            self.append_from_thread(f"Błąd: {e}")
        finally:
            self.after(0, self.finish_work)


if __name__ == "__main__":
    app = JarvisGUI()
    app.mainloop()
