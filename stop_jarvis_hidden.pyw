import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
LOGS_DIR = ROOT_DIR / "logs"


def hidden_creationflags():
    if not sys.platform.startswith("win"):
        return 0
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def log(message):
    LOGS_DIR.mkdir(exist_ok=True)
    with (LOGS_DIR / "stop.log").open("a", encoding="utf-8") as log_file:
        log_file.write(message + "\n")


def run_command(args):
    return subprocess.run(
        args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        shell=False,
        creationflags=hidden_creationflags(),
    )


def pids_for_port(port):
    result = run_command(["netstat", "-ano"])
    if result.returncode != 0:
        return set()

    pids = set()
    marker = f":{port}"
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address = parts[1]
        state_or_pid = parts[-2]
        pid = parts[-1]
        if marker in local_address and state_or_pid.upper() == "LISTENING" and pid.isdigit():
            pids.add(pid)
    return pids


def kill_pid(pid, reason):
    result = run_command(["taskkill", "/PID", str(pid), "/T", "/F"])
    if result.returncode == 0:
        log(f"Zamknięto {reason}: PID {pid}")
    else:
        log(f"Nie udało się zamknąć {reason}: PID {pid}")


def kill_ports():
    for port, name in [(8000, "Backend"), (8001, "Processor")]:
        pids = pids_for_port(port)
        if not pids:
            log(f"{name} nie działa na porcie {port}")
            continue
        for pid in pids:
            kill_pid(pid, f"{name} port {port}")


def kill_python_processes_by_command(markers):
    marker_conditions = " -or ".join([f"$_.CommandLine -like '*{marker}*'" for marker in markers])
    command = (
        "Get-CimInstance Win32_Process | "
        f"Where-Object {{ $_.ProcessId -ne $PID -and ({marker_conditions}) }} | "
        "ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Output $_.ProcessId }"
    )
    result = run_command(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command])
    if result.returncode != 0:
        log("Nie udało się sprawdzić procesów Jarvisa po command line")
        return

    pids = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not pids:
        log("Nie znaleziono procesów jarvis_agent.py/control_center.py")
        return
    for pid in pids:
        log(f"Zamknięto proces Jarvisa: PID {pid}")


def main():
    if not sys.platform.startswith("win"):
        log("stop_jarvis_hidden.pyw jest przygotowany dla Windows.")
        return
    kill_ports()
    kill_python_processes_by_command(["jarvis_agent.py", "control_center.py"])
    log("Stop Jarvis zakończony.")


if __name__ == "__main__":
    main()
