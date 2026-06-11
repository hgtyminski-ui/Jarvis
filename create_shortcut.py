import os
import sys
from pathlib import Path


ROOT_DIR = Path(r"C:\Users\User\Documents\Jarvis")
SHORTCUT_NAME = "Jarvis Control Center.lnk"
TARGET_PATH = ROOT_DIR / "start_jarvis.bat"
ICON_PATH = ROOT_DIR / "jarvis_icon.ico"


def desktop_path():
    return Path(os.path.join(os.path.expanduser("~"), "Desktop"))


def main():
    try:
        import win32com.client
    except ImportError:
        print("Brakuje pywin32. Zainstaluj:")
        print("pip install pywin32")
        return 1

    if not TARGET_PATH.exists():
        print(f"Nie znaleziono targetu skrótu: {TARGET_PATH}")
        return 1

    shortcut_path = desktop_path() / SHORTCUT_NAME
    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(shortcut_path))
    shortcut.TargetPath = str(TARGET_PATH)
    shortcut.WorkingDirectory = str(ROOT_DIR)
    shortcut.Description = "Jarvis Control Center"

    icon_used = False
    if ICON_PATH.exists():
        shortcut.IconLocation = str(ICON_PATH)
        icon_used = True

    shortcut.Save()

    print(f"Utworzono skrót: {shortcut_path}")
    print(f"Target: {TARGET_PATH}")
    print(f"Folder roboczy: {ROOT_DIR}")
    print(f"Ikona: {'użyto ' + str(ICON_PATH) if icon_used else 'brak jarvis_icon.ico, użyto domyślnej'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
