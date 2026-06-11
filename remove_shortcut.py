import os
from pathlib import Path


SHORTCUT_NAME = "Jarvis Control Center.lnk"


def desktop_path():
    return Path(os.path.join(os.path.expanduser("~"), "Desktop"))


def main():
    shortcut_path = desktop_path() / SHORTCUT_NAME
    if not shortcut_path.exists():
        print(f"Skrót nie istnieje: {shortcut_path}")
        return 0

    shortcut_path.unlink()
    print(f"Usunięto skrót: {shortcut_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
