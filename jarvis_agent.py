import asyncio
import json
from urllib.parse import quote

import websockets

from actions import close_app, open_app
from config import load_config


DEFAULT_DEVICE_ID = "hubert-pc"
DEFAULT_HUB_URL = "ws://127.0.0.1:8002"
DEFAULT_AUTH_TOKEN = "dev-token"
RECONNECT_SECONDS = 5


def load_agent_config():
    try:
        config = load_config()
    except Exception:
        config = {}

    device_id = str(config.get("device_id") or DEFAULT_DEVICE_ID)
    hub_url = str(config.get("hub_url") or DEFAULT_HUB_URL)
    auth_token = str(config.get("auth_token") or DEFAULT_AUTH_TOKEN)
    return device_id, normalize_hub_url(hub_url), auth_token


def normalize_hub_url(hub_url):
    normalized = hub_url.rstrip("/")
    if normalized.startswith("http://"):
        return "ws://" + normalized[len("http://"):]
    if normalized.startswith("https://"):
        return "wss://" + normalized[len("https://"):]
    return normalized


def command_value(command, *names, default=""):
    for name in names:
        value = command.get(name)
        if value:
            return str(value).strip().lower()

    parameters = command.get("parameters")
    if isinstance(parameters, dict):
        for name in names:
            value = parameters.get(name)
            if value:
                return str(value).strip().lower()

    return default


async def handle_command(command):
    if not isinstance(command, dict):
        print("Unknown action")
        return

    action = str(command.get("action") or "").strip().lower()

    if action == "open_app":
        app_name = command_value(command, "app", "target")
        if not app_name:
            print("Unknown action")
            return
        result = open_app(app_name)
        print(f"open_app {app_name}: {result}")
        return

    if action == "close_app":
        app_name = command_value(command, "app", "target")
        if not app_name:
            print("Unknown action")
            return
        result = close_app(app_name)
        if result == "not_running" and app_name == "whatsapp":
            print("WhatsApp nie był uruchomiony.")
        else:
            print(f"close_app {app_name}: {result}")
        return

    if action == "chat":
        response = command.get("response") or command.get("message") or ""
        print(response)
        return

    print("Unknown action")


async def run_agent():
    device_id, hub_url, auth_token = load_agent_config()
    websocket_url = f"{hub_url}/agent/connect/{device_id}?token={quote(auth_token, safe='')}"

    while True:
        try:
            print(f"Connecting Jarvis Agent: {websocket_url}")
            async with websockets.connect(websocket_url) as websocket:
                print(f"Jarvis Agent connected as {device_id}")
                async for message in websocket:
                    try:
                        command = json.loads(message)
                    except json.JSONDecodeError:
                        print("Unknown action")
                        continue
                    await handle_command(command)
        except Exception as e:
            print(f"Jarvis Agent disconnected: {e}")
            await asyncio.sleep(RECONNECT_SECONDS)


if __name__ == "__main__":
    asyncio.run(run_agent())
