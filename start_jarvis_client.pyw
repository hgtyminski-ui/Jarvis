import os
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
LOGS_DIR = ROOT_DIR / "logs"


def pythonw_executable():
    executable = Path(sys.executable)
    if executable.name.lower() == "python.exe":
        pythonw = executable.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(executable)


def hidden_creationflags():
    if not sys.platform.startswith("win"):
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def main():
    LOGS_DIR.mkdir(exist_ok=True)
    log_path = LOGS_DIR / "jarvis_client.log"
    log_file = log_path.open("a", encoding="utf-8")
    log_file.write("\n--- Starting Jarvis Desktop Client ---\n")
    log_file.flush()

    env = os.environ.copy()
    env["JARVIS_FORCE_CLIENT"] = "1"
    env["JARVIS_RUNTIME_MODE"] = "client"

    subprocess.Popen(
        [pythonw_executable(), "control_center.py"],
        cwd=str(ROOT_DIR),
        stdin=subprocess.DEVNULL,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=hidden_creationflags(),
        close_fds=False,
        env=env,
    )


if __name__ == "__main__":
    main()
