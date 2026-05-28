# Jarvis Processor

Eksperymentalny serwis interpretacji tekstu dla docelowej architektury Hub/Processor/Agent.

## Uruchomienie

```powershell
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8001
```

## Przykłady normalizacji notatek

- Input: `zapisz że jutro mam dentystę`
  Output `parameters.content`: `Jutro mam dentystę.`
- Input: `zapisz mi że trening jest o 18`
  Output `parameters.content`: `Trening jest o 18.`
- Input: `zanotuj kupić karmę dla psa`
  Output `parameters.content`: `Kupić karmę dla psa.`

## Konfiguracja

Skopiuj `.env.example` do `.env` i dostosuj ustawienia LLM, jeśli potrzebujesz:

```env
LLM_PROVIDER=lmstudio
LLM_BASE_URL=http://127.0.0.1:1233/v1
LLM_MODEL=local-model
LLM_API_KEY=lm-studio
```

## Test

PowerShell:

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8001/interpret `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"text":"otwórz spotify"}'
```

curl:

```bash
curl -X POST http://127.0.0.1:8001/interpret \
  -H "Content-Type: application/json" \
  -d '{"text":"otwórz spotify"}'
```
