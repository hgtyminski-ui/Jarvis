import socket
import subprocess
import sys
import urllib.error
import urllib.request
import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
PROCESSOR_DIR = ROOT_DIR / "services" / "jarvis-processor"
LOGS_DIR = ROOT_DIR / "logs"
LM_STUDIO_MODELS_URL = "http://127.0.0.1:1233/v1/models"
CONFIG_PATH = ROOT_DIR / "config.json"


def python_executable():
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        python_exe = executable.with_name("python.exe")
        if python_exe.exists():
            return str(python_exe)
    return str(executable)


def load_runtime_mode():
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return "local_full"
    mode = str(config.get("runtime_mode") or "local_full")
    return mode if mode in {"local_full", "client", "server"} else "local_full"


def write_launcher_log(message):
    LOGS_DIR.mkdir(exist_ok=True)
    with (LOGS_DIR / "launcher.log").open("a", encoding="utf-8") as log_file:
        log_file.write(message + "\n")


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


def hidden_creationflags():
    if not sys.platform.startswith("win"):
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def popen_process(name, args, cwd, log_filename):
    LOGS_DIR.mkdir(exist_ok=True)
    log_path = LOGS_DIR / log_filename
    log_file = log_path.open("a", encoding="utf-8")
    log_file.write(f"\n--- Starting {name} hidden ---\n")
    log_file.flush()

    subprocess.Popen(
        args,
        cwd=str(cwd),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        creationflags=hidden_creationflags(),
        close_fds=False,
    )
    write_launcher_log(f"{name} uruchomiony. Log: {log_path}")


def start_backend(python_cmd):
    if is_port_open("127.0.0.1", 8000):
        write_launcher_log("Backend już działa")
        return
    popen_process(
        "Backend",
        [python_cmd, "-m", "uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"],
        ROOT_DIR,
        "backend.log",
    )


def start_processor(python_cmd):
    if is_port_open("127.0.0.1", 8001):
        write_launcher_log("Processor już działa")
        return
    popen_process(
        "Processor",
        [python_cmd, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", "8001"],
        PROCESSOR_DIR,
        "processor.log",
    )


def start_agent(python_cmd):
    popen_process("Agent", [python_cmd, "jarvis_agent.py"], ROOT_DIR, "agent.log")


def start_control_center(python_cmd):
    popen_process("Control Center", [python_cmd, "control_center.py"], ROOT_DIR, "control_center.log")


def main():
    LOGS_DIR.mkdir(exist_ok=True)
    python_cmd = python_executable()
    runtime_mode = load_runtime_mode()

    write_launcher_log(f"Runtime mode: {runtime_mode}")
    if runtime_mode == "client":
        write_launcher_log("Client mode: uruchamiam tylko Jarvis Desktop Client.")
        start_control_center(python_cmd)
    elif runtime_mode == "server":
        if check_lm_studio():
            write_launcher_log("LM Studio dziala")
        else:
            write_launcher_log("LM Studio nie dziala. Uruchom Local Server w LM Studio.")
        start_backend(python_cmd)
        start_processor(python_cmd)
    else:
        if check_lm_studio():
            write_launcher_log("LM Studio dziala")
        else:
            write_launcher_log("LM Studio nie dziala. Uruchom Local Server w LM Studio.")
        start_backend(python_cmd)
        start_processor(python_cmd)
        start_agent(python_cmd)
        start_control_center(python_cmd)

    write_launcher_log("Ukryty launcher zakonczyl uruchamianie procesow.")

if __name__ == "__main__":
    main()

