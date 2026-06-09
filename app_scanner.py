import json
import os
import re
import shutil
import unicodedata
from argparse import ArgumentParser
from pathlib import Path

from path_utils import get_base_path


APPS_PATH = get_base_path() / "apps.json"
MAX_EXE_DEPTH = 4
MAX_DISCOVERED_APPS = 300
MAX_CLEANED_APPS = 300
JUNK_PATTERNS = [
    "uninstall",
    "unins",
    "unins000",
    "setup",
    "installer",
    "updater",
    "update",
    "crash",
    "crashpad",
    "helper",
    "service",
    "daemon",
    "runtime",
    "maintenance",
    "redistributable",
    "vc_redist",
    "directx",
    "repair",
    "package",
    "driver",
    "telemetry",
    "background",
    "broker",
    "bootstrap",
    "notification",
    "crashreport",
    "errorreport",
    "reporter",
    "codec",
    "license",
    "readme",
    "manual",
    "documentation",
    "webview",
    "pwa",
    "stub",
    "proxy",
    "util",
    "shortcut",
    "skrot",
    "plugin",
    "authenticator",
    "capture",
    "connector",
    "exporter",
    "hidden",
    ".vbs",
]
SKIP_DIR_NAMES = {
    "$recycle.bin",
    "cache",
    "crashpad",
    "debug",
    "diagnostics",
    "driver",
    "drivers",
    "installer",
    "maintenance",
    "packages",
    "redist",
    "redistributable",
    "resources",
    "runtimes",
    "locales",
    "node_modules",
    "temp",
    "tmp",
    "uninstall",
    "update",
    "updates",
}
KNOWN_APP_PATTERNS = [
    "codex",
    "chatgpt",
    "cursor",
    "chrome",
    "edge",
    "firefox",
    "brave",
    "opera",
    "spotify",
    "discord",
    "steam",
    "epic games",
    "epic_games",
    "vscode",
    "visual studio code",
    "visual_studio_code",
    "pycharm",
    "minecraft",
    "roblox",
    "obs",
    "capcut",
    "obs studio",
    "obs_studio",
    "epic games launcher",
    "epic_games_launcher",
    "minecraft launcher",
    "minecraft_launcher",
    "whatsapp",
    "teams",
    "zoom",
    "netflix",
    "youtube",
]
KNOWN_APP_LABELS = [
    "Codex",
    "ChatGPT",
    "Visual Studio Code",
    "Cursor",
    "Google Chrome",
    "Microsoft Edge",
    "Spotify",
    "Discord",
    "Steam",
    "Epic Games Launcher",
    "Roblox",
    "Minecraft Launcher",
    "OBS Studio",
    "CapCut",
]


def normalize_app_key(name):
    normalized = str(name or "").strip().lower()
    normalized = unicodedata.normalize("NFKD", normalized).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"\.(exe|lnk|url)$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized or "app"


def app_label_from_path(path):
    return Path(path).stem.replace("_", " ").strip() or Path(path).name


def is_junk_name(name):
    lowered = str(name or "").lower()
    return any(pattern in lowered for pattern in JUNK_PATTERNS)


def is_known_app_name(name):
    normalized = normalize_app_key(name).replace("_", " ")
    lowered = str(name or "").lower()
    return any(pattern in lowered or pattern in normalized for pattern in KNOWN_APP_PATTERNS)


def app_quality_score(key, entry):
    label = str(entry.get("label") if isinstance(entry, dict) else key)
    launch_path = app_launch_value(entry)
    app_type = entry.get("type") if isinstance(entry, dict) else ""
    score = 0

    if is_known_app_name(f"{key} {label}"):
        score += 80
    if app_type == "lnk":
        score += 40
    elif app_type == "uri":
        score += 30
    elif app_type == "exe":
        score += 10
    elif app_type == "command":
        score += 45
    if "\\start menu\\programs\\" in str(launch_path).lower():
        score += 20
    if "\\desktop" in str(launch_path).lower():
        score += 15
    if not is_junk_name(f"{key} {label} {launch_path}"):
        score += 10
    return score


def limit_discovered_apps(discovered, limit=MAX_DISCOVERED_APPS):
    ranked = sorted(
        discovered.items(),
        key=lambda item: (-app_quality_score(item[0], item[1]), str(item[1].get("label", item[0])).lower()),
    )
    return dict(ranked[:limit])


def is_probably_system_or_library(path):
    lowered = str(path).lower()
    suffix = Path(path).suffix.lower()
    if suffix in {".dll", ".sys", ".msi"}:
        return True
    blocked_parts = [
        "\\windows\\",
        "\\system32\\",
        "\\syswow64\\",
        "\\node_modules\\",
        "\\packages\\",
        "\\runtimes\\",
        "\\resources\\",
        "\\locales\\",
        "\\cache\\",
        "\\temp\\",
    ]
    return any(part in lowered for part in blocked_parts)


def unique_key(base_key, apps):
    key = base_key
    index = 2
    while key in apps:
        key = f"{base_key}_{index}"
        index += 1
    return key


def read_lnk_target(path):
    try:
        import winshell

        shortcut = winshell.shortcut(str(path))
        target = shortcut.path
        return target if target else None
    except Exception:
        pass

    try:
        import pythoncom
        from win32com.client import Dispatch

        pythoncom.CoInitialize()
        shell = Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(str(path))
        target = shortcut.Targetpath
        return target if target else None
    except Exception:
        return None


def make_app_entry(label, launch_path, app_type, target_path=None):
    entry = {
        "label": label,
        "type": app_type,
        "discovered": True,
        "hidden": False,
    }
    if app_type == "command":
        entry["command"] = str(launch_path)
    else:
        entry["launch_path"] = str(launch_path)
    if app_type == "exe":
        entry["path"] = str(launch_path)
    if target_path:
        entry["target_path"] = str(target_path)
        if Path(str(target_path)).suffix.lower() == ".exe":
            entry["process"] = Path(str(target_path)).name
    elif Path(str(launch_path)).suffix.lower() == ".exe":
        entry["process"] = Path(str(launch_path)).name
    return entry


def add_discovered_app(discovered, label, launch_path, app_type, target_path=None):
    combined = f"{label} {launch_path} {target_path or ''}"
    if not label or is_junk_name(combined) or is_probably_system_or_library(launch_path):
        return
    if target_path and is_probably_system_or_library(target_path):
        return

    base_key = normalize_app_key(label)
    if base_key in discovered:
        return

    key = unique_key(base_key, discovered)
    entry = make_app_entry(label, launch_path, app_type, target_path)
    entry["key"] = key
    entry["name"] = key
    discovered[key] = entry


def start_menu_and_desktop_paths():
    user_profile = Path.home()
    return [
        Path(os.environ.get("ProgramData", r"C:\ProgramData")) / r"Microsoft\Windows\Start Menu\Programs",
        user_profile / r"AppData\Roaming\Microsoft\Windows\Start Menu\Programs",
        user_profile / "Desktop",
        Path(r"C:\Users\Public\Desktop"),
    ]


def program_paths():
    user_profile = Path.home()
    paths = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
        user_profile / r"AppData\Local\Programs",
    ]
    return [path for path in paths if path.exists()]


def known_app_search_roots():
    user_profile = Path.home()
    roots = [
        user_profile / r"AppData\Local\Programs",
        user_profile / r"AppData\Local",
        user_profile / r"AppData\Roaming",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
    ]
    return [root for root in roots if root.exists()]


def scan_shortcuts(discovered):
    for root in start_menu_and_desktop_paths():
        if not root.exists():
            continue

        for shortcut in root.rglob("*"):
            if shortcut.suffix.lower() not in {".lnk", ".url"}:
                continue
            if is_junk_name(str(shortcut)):
                continue

            label = app_label_from_path(shortcut)
            if shortcut.suffix.lower() == ".lnk":
                target_path = read_lnk_target(shortcut)
                add_discovered_app(discovered, label, shortcut, "lnk", target_path)
            else:
                add_discovered_app(discovered, label, shortcut, "uri")


def should_skip_dir(path):
    name = path.name.lower()
    return name in SKIP_DIR_NAMES or is_junk_name(name)


def scan_executables(discovered):
    for root in program_paths():
        root_depth = len(root.parts)
        for current_root, dir_names, file_names in os.walk(root):
            current_path = Path(current_root)
            depth = len(current_path.parts) - root_depth
            if depth >= MAX_EXE_DEPTH:
                dir_names[:] = []
            else:
                dir_names[:] = [name for name in dir_names if not should_skip_dir(current_path / name)]

            for file_name in file_names:
                if not file_name.lower().endswith(".exe") or is_junk_name(file_name):
                    continue
                exe_path = current_path / file_name
                if is_probably_system_or_library(exe_path):
                    continue
                add_discovered_app(discovered, app_label_from_path(exe_path), exe_path, "exe")


def add_command_app(discovered, key, label, command):
    if key in discovered:
        return
    entry = make_app_entry(label, command, "command")
    entry["key"] = key
    entry["name"] = key
    discovered[key] = entry


def scan_codex(discovered):
    if shutil.which("codex"):
        add_command_app(discovered, "codex", "Codex", "codex")

    for root in [Path.home() / r"AppData\Local", Path.home() / r"AppData\Roaming"]:
        if not root.exists():
            continue
        for folder in root.iterdir():
            if "codex" not in folder.name.lower() or not folder.is_dir() or should_skip_dir(folder):
                continue
            for exe_path in folder.rglob("*.exe"):
                if is_junk_name(str(exe_path)) or is_probably_system_or_library(exe_path):
                    continue
                add_discovered_app(discovered, "Codex", exe_path, "exe")
                return


def scan_known_app_folders(discovered):
    wanted_keys = {normalize_app_key(label): label for label in KNOWN_APP_LABELS}
    for root in known_app_search_roots():
        for child in root.iterdir():
            if not child.is_dir() or should_skip_dir(child):
                continue
            child_key = normalize_app_key(child.name)
            matched_label = None
            for wanted_key, label in wanted_keys.items():
                if wanted_key in child_key or child_key in wanted_key:
                    matched_label = label
                    break
            if not matched_label:
                continue
            for exe_path in child.rglob("*.exe"):
                if is_junk_name(str(exe_path)) or is_probably_system_or_library(exe_path):
                    continue
                add_discovered_app(discovered, matched_label, exe_path, "exe")
                break


def scan_installed_apps(deep_scan=False):
    discovered = {}
    scan_shortcuts(discovered)
    scan_codex(discovered)
    scan_known_app_folders(discovered)
    if deep_scan:
        scan_executables(discovered)
    return limit_discovered_apps(discovered)


def load_existing_apps():
    if not APPS_PATH.exists():
        return {}
    try:
        data = json.loads(APPS_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def app_launch_value(entry):
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return entry.get("command") or entry.get("launch_path") or entry.get("path") or entry.get("uri") or ""
    return ""


def merge_discovered_apps(existing_apps, discovered_apps):
    merged = dict(existing_apps or {})
    existing_keys = {str(key).lower() for key in merged}
    existing_launches = {
        str(app_launch_value(value)).lower()
        for value in merged.values()
        if app_launch_value(value)
    }

    for key, entry in (discovered_apps or {}).items():
        normalized_key = normalize_app_key(key)
        launch_value = str(app_launch_value(entry)).lower()
        if normalized_key in existing_keys or (launch_value and launch_value in existing_launches):
            continue

        final_key = unique_key(normalized_key, merged)
        if isinstance(entry, dict):
            entry = dict(entry)
            entry["key"] = final_key
            entry["name"] = final_key
        merged[final_key] = entry
        existing_keys.add(final_key.lower())
        if launch_value:
            existing_launches.add(launch_value)

    return merged


def should_keep_discovered_app(key, entry):
    if not isinstance(entry, dict):
        return False

    label = str(entry.get("label") or key)
    launch_value = app_launch_value(entry)
    target_path = str(entry.get("target_path") or "")
    combined = f"{key} {label} {launch_value} {target_path}"

    if is_junk_name(combined):
        return False
    if launch_value and is_probably_system_or_library(launch_value):
        return False
    if target_path and is_probably_system_or_library(target_path):
        return False
    if is_known_app_name(combined):
        return True
    if entry.get("type") in {"lnk", "uri"}:
        return app_quality_score(key, entry) >= 55
    return app_quality_score(key, entry) >= 25


def clean_apps_json(apps=None, max_apps=MAX_CLEANED_APPS):
    original_apps = load_existing_apps() if apps is None else dict(apps or {})
    manual_apps = {}
    discovered_apps = {}

    for key, entry in original_apps.items():
        if not isinstance(key, str) or not key.strip():
            continue

        if isinstance(entry, dict) and entry.get("discovered") is True:
            if should_keep_discovered_app(key, entry):
                discovered_apps[key] = entry
            continue

        manual_apps[key] = entry

    remaining_slots = max(0, max_apps - len(manual_apps))
    kept_discovered = limit_discovered_apps(discovered_apps, remaining_slots)
    cleaned_apps = dict(manual_apps)
    cleaned_apps.update(kept_discovered)
    save_apps_json(cleaned_apps)

    return {
        "apps": cleaned_apps,
        "before": len(original_apps),
        "after": len(cleaned_apps),
        "removed": len(original_apps) - len(cleaned_apps),
    }


def save_apps_json(apps):
    APPS_PATH.write_text(json.dumps(apps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    parser = ArgumentParser(description="Jarvis app scanner")
    parser.add_argument("--clean", action="store_true", help="wyczysc smieciowe wpisy discovered=true z apps.json")
    parser.add_argument("--scan", action="store_true", help="skanuj Start Menu i Desktop")
    parser.add_argument("--deep-scan", action="store_true", help="skanuj takze Program Files z mocnym filtrem")
    args = parser.parse_args()

    if args.clean:
        result = clean_apps_json()
        print(f"Wyczyszczono apps.json: usunieto {result['removed']}, zostalo {result['after']}.")
        return 0

    existing_apps = load_existing_apps()
    discovered_apps = scan_installed_apps(deep_scan=args.deep_scan)
    merged_apps = merge_discovered_apps(existing_apps, discovered_apps)
    save_apps_json(merged_apps)

    found = len(discovered_apps)
    added = len(merged_apps) - len(existing_apps)
    print(f"Znaleziono {found} aplikacji, dodano {added} nowych.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
