import sys
from pathlib import Path


DATA_FILES = ["config.json", "apps.json", "aliases.json", "processes.json", "app_categories.json"]


def get_base_path():
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        if any((exe_dir / file_name).exists() for file_name in DATA_FILES):
            return exe_dir

        return Path(getattr(sys, "_MEIPASS", exe_dir)).resolve()

    return Path(__file__).resolve().parent
