import json
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_TIMEOUT = 10


class JarvisApiError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def normalize_base_url(base_url):
    return str(base_url or "").strip().rstrip("/")


def auth_headers(token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Jarvis-Token"] = str(token)
    return headers


def request_json(method, base_url, path, token=None, payload=None, timeout=DEFAULT_TIMEOUT):
    base_url = normalize_base_url(base_url)
    if not base_url:
        raise JarvisApiError("Brak adresu serwera.")

    data = None
    headers = auth_headers(token)
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request = urllib.request.Request(
        f"{base_url}{path}",
        data=data,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise JarvisApiError("Unauthorized", status=401) from error
        try:
            body = error.read().decode("utf-8")
            payload = json.loads(body) if body else {}
            detail = payload.get("detail") if isinstance(payload, dict) else None
        except Exception:
            detail = None
        raise JarvisApiError(detail or f"HTTP {error.code}", status=error.code) from error
    except Exception as error:
        raise JarvisApiError("Brak polaczenia z serwerem.") from error


def get_status(base_url, token=None):
    return request_json("GET", base_url, "/status", token=token, timeout=3)[1]


def send_chat_message(base_url, token, message, device_id=None):
    payload = {"text": message, "device_id": device_id or "local-pc"}
    try:
        return request_json("POST", base_url, "/process-text", token=token, payload=payload, timeout=14)[1]
    except JarvisApiError as error:
        if error.status == 404:
            return request_json(
                "POST",
                base_url,
                "/chat",
                token=token,
                payload={"message": message},
                timeout=14,
            )[1]
        raise


def list_notes(base_url, token):
    data = request_json("GET", base_url, "/notes", token=token, timeout=8)[1]
    if isinstance(data, dict):
        notes = data.get("notes", [])
    elif isinstance(data, list):
        notes = data
    else:
        notes = []
    return notes if isinstance(notes, list) else []


def get_note(base_url, token, note_id):
    encoded = urllib.parse.quote(str(note_id), safe="")
    return request_json("GET", base_url, f"/notes/{encoded}", token=token, timeout=8)[1]


def create_note(base_url, token, title, content):
    return request_json(
        "POST",
        base_url,
        "/notes",
        token=token,
        payload={"title": title or "", "content": content or ""},
        timeout=10,
    )[1]


def delete_note(base_url, token, note_id):
    encoded = urllib.parse.quote(str(note_id), safe="")
    return request_json("DELETE", base_url, f"/notes/{encoded}", token=token, timeout=8)[1]


def scan_apps(base_url, token):
    return request_json("POST", base_url, "/apps/scan", token=token, payload={}, timeout=60)[1]


def pairing_info(base_url, token=None):
    return request_json("GET", base_url, "/pairing/info", token=token, timeout=5)[1]
