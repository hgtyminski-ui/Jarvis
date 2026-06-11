import os
import sys
from pathlib import Path


ROOT_DIR = Path(r"C:\Users\User\Documents\Jarvis")
START_SHORTCUT_NAME = "Jarvis Control Center.lnk"
STOP_SHORTCUT_NAME = "Stop Jarvis.lnk"
START_TARGET_PATH = ROOT_DIR / "start_jarvis_hidden.pyw"
STOP_TARGET_PATH = ROOT_DIR / "stop_jarvis_hidden.pyw"
ICON_PATH = ROOT_DIR / "jarvis_icon.ico"


def desktop_path():
    return Path(os.path.join(os.path.expanduser("~"), "Desktop"))


def create_shortcut(shell, shortcut_name, target_path, description):
    if not target_path.exists():
        print(f"Nie znaleziono targetu skrótu: {target_path}")
        return False

    shortcut_path = desktop_path() / shortcut_name
    shortcut = shell.CreateShortcut(str(shortcut_path))
    shortcut.TargetPath = str(target_path)
    shortcut.WorkingDirectory = str(ROOT_DIR)
    shortcut.Description = description

    icon_used = False
    if ICON_PATH.exists():
        shortcut.IconLocation = str(ICON_PATH)
        icon_used = True

    shortcut.Save()
    print(f"Utworzono skrót: {shortcut_path}")
    print(f"Target: {target_path}")
    print(f"Folder roboczy: {ROOT_DIR}")
    print(f"Ikona: {'użyto ' + str(ICON_PATH) if icon_used else 'brak jarvis_icon.ico, użyto domyślnej'}")
    return True


def main():
    try:
        import win32com.client
    except ImportError:
        print("Brakuje pywin32. Zainstaluj:")
        print("pip install pywin32")
        return 1

    shell = win32com.client.Dispatch("WScript.Shell")
    start_ok = create_shortcut(shell, START_SHORTCUT_NAME, START_TARGET_PATH, "Jarvis Control Center")
    stop_ok = create_shortcut(shell, STOP_SHORTCUT_NAME, STOP_TARGET_PATH, "Stop Jarvis")
    return 0 if start_ok and stop_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
