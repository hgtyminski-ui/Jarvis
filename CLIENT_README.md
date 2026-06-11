# Jarvis Desktop Client

Jarvis Desktop Client to aplikacja dla znajomych Huberta. Dziala jako zwykly klient Windows i laczy sie z Jarvis Server przez internet.

Nie uruchamia lokalnie backendu, processora, agenta, LM Studio ani terminali.

## Pierwsze uruchomienie

1. Uruchom Jarvis Desktop Client.
2. Wpisz `Server URL` otrzymany od Huberta.
3. Wpisz `API Token` otrzymany od Huberta.
4. Wpisz `Device ID`, np. `ania-pc` albo `client-pc`.
5. Kliknij `Test polaczenia`.
6. Kliknij `Zapisz i polacz`.

## Funkcje klienta

- Chat z Jarvisem przez remote Jarvis Server.
- Lista notatek przypisana do Twojego tokenu.
- Tworzenie i usuwanie notatek na serwerze.
- Status polaczenia z Jarvis Server.

## Czego klient nie wymaga

- Python instalowany recznie przez uzytkownika po spakowaniu do instalatora.
- Lokalny backend.
- Lokalny processor.
- LM Studio.
- Terminal.

## Konfiguracja dla instalatora

Przy pakowaniu klienta uzyj konfiguracji w stylu `client_config.example.json` albo ustaw `runtime_mode` na `client` w dolaczonym `config.json`.

Launcher klienta:

```powershell
start_jarvis_client.pyw
```

Ten launcher wymusza tryb `client` i odpala tylko `control_center.py`.
