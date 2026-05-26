# Jarvis Hub

Eksperymentalny serwis Hub dla docelowej architektury Hub/Processor/Agent.

Hub:
- przyjmuje tekst przez `POST /process-text`,
- wysyła tekst do Jarvis Processor,
- odbiera `command` JSON,
- przekazuje komendę do podłączonego agenta przez WebSocket.

## Uruchomienie

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

## Wymagania

- Jarvis Processor działa na `127.0.0.1:8001`.
- Agent łączy się przez WebSocket: `/agent/connect/{device_id}`.
- Endpointy `/agents` i `/process-text` wymagają nagłówka `X-Jarvis-Token`.
- Domyślny token developerski: `dev-token`.

## Konfiguracja

Skopiuj `.env.example` do `.env`:

```env
AUTH_TOKEN=dev-token
JARVIS_PROCESSOR_URL=http://127.0.0.1:8001
```

## Test /process-text

PowerShell:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8000/process-text `
  -Method Post `
  -Headers @{ "X-Jarvis-Token" = "dev-token" } `
  -ContentType "application/json" `
  -Body '{"text":"otwórz spotify","device_id":"hubert-pc"}'
```
