import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
PROCESSOR_DIR = ROOT_DIR / "services" / "jarvis-processor"
LOGS_DIR = ROOT_DIR / "logs"
LM_STUDIO_MODELS_URL = "http://127.0.0.1:1233/v1/models"


def log(message):
    print(message, flush=True)


def is_port_open(host, port, timeout=1.0):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def check_lm_studio():
    request = urllib.request.Request(LM_STUDIO_MODELS_URL, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def popen_process(name, args, cwd, log_filename):
    LOGS_DIR.mkdir(exist_ok=True)
    log_path = LOGS_DIR / log_filename
    log_file = log_path.open("a", encoding="utf-8")
    log_file.write(f"\n--- Starting {name} ---\n")
    log_file.flush()

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    subprocess.Popen(
        args,
        cwd=str(cwd),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    log(f"{name} uruchomiony. Log: {log_path}")


def start_backend():
    if is_port_open("127.0.0.1", 8000):
        log("Backend już działa")
        return

    popen_process(
        "Backend",
        [sys.executable, "-m", "uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"],
        ROOT_DIR,
        "backend.log",
    )


def start_processor():
    if is_port_open("127.0.0.1", 8001):
        log("Processor już działa")
        return

    popen_process(
        "Processor",
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8001"],
        PROCESSOR_DIR,
        "processor.log",
    )


def start_agent():
    popen_process(
        "Agent",
        [sys.executable, "jarvis_agent.py"],
        ROOT_DIR,
        "agent.log",
    )


def start_control_center():
    popen_process(
        "Control Center",
        [sys.executable, "control_center.py"],
        ROOT_DIR,
        "control_center.log",
    )


def main():
    LOGS_DIR.mkdir(exist_ok=True)

    if check_lm_studio():
        log("LM Studio działa")
    else:
        log("LM Studio nie działa. Uruchom Local Server w LM Studio.")

    start_backend()
    start_processor()
    start_agent()
    start_control_center()

    log("Jarvis launcher zakończył uruchamianie procesów.")


if __name__ == "__main__":
    main()
