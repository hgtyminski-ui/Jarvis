# Jarvis

Jarvis to prosty asystent tekstowo-glosowy w Pythonie. Program laczy sie z lokalnym modelem przez serwer LM Studio, rozpoznaje intencje uzytkownika i potrafi m.in. otwierac wybrane aplikacje oraz strony.

## Wymagania

- Windows
- Python 3
- LM Studio z pobranym modelem
- Zaleznosci z pliku `requirements.txt`

Instalacja zaleznosci:

```bash
pip install -r requirements.txt
```

## Uruchomienie LM Studio server

1. Otworz LM Studio.
2. Wybierz pobrany model.
3. Przejdz do zakladki lokalnego serwera.
4. Uruchom server OpenAI-compatible.
5. Sprawdz, czy adres zgadza sie z `base_url` w `config.json`, np. `http://127.0.0.1:1233/v1`.

## Uruchomienie Jarvisa

```bash
python main.py
```

Po starcie wpisuj komendy w konsoli. Aby zakonczyc, uzyj `/exit` albo jednej z komend wyjscia z `config.json`.

## Komendy lokalne

- `/help` - pokazuje dostepne komendy
- `/status` - sprawdza polaczenie z LM Studio
- `/clear` - czysci historie rozmowy z RAM
- `/listen` - nagrywa krotka wiadomosc z mikrofonu
- `/exit` - konczy program

## Aplikacje i aliasy

Aplikacje sa zdefiniowane w `apps.json`. Klucz to nazwa aplikacji, a wartosc to komenda, sciezka, skrot `.lnk`, plik `.url` albo URI.

Aliasy sa zdefiniowane w `aliases.json`. Plik mapuje nazwe docelowa na liste aliasow, np. `yt` i `jutub` moga wskazywac na `youtube`.

## config.json

`config.json` zawiera podstawowe ustawienia Jarvisa:

- `assistant_name` - nazwa asystenta
- `base_url`, `model`, `temperature` - ustawienia polaczenia z LM Studio
- `system_message` - instrukcja systemowa dla modelu
- `voice_enabled` i ustawienia `voice_*` / `edge_*` - konfiguracja glosu
- `microphone_device`, `sample_rate`, `record_seconds` - ustawienia mikrofonu
- `whisper_model`, `whisper_device`, `whisper_compute_type` - ustawienia rozpoznawania mowy
