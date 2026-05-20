from pathlib import Path

from config import load_config


INPUT_FILE = Path(__file__).with_name("input.wav")
FALLBACK_SAMPLE_RATES = [48000, 44100, 16000]
WHISPER_MODELS = {}


def get_sample_rates(config):
    sample_rates = [config.get("sample_rate", 48000)]

    for sample_rate in FALLBACK_SAMPLE_RATES:
        if sample_rate not in sample_rates:
            sample_rates.append(sample_rate)

    return sample_rates


def record_audio(sd, sample_rate, microphone_device, duration):
    recording = sd.rec(
        int(duration * sample_rate),
        samplerate=sample_rate,
        channels=1,
        dtype="int16",
        device=microphone_device,
    )
    sd.wait()

    return recording


def get_whisper_model(model_name, device, compute_type):
    from faster_whisper import WhisperModel

    key = (model_name, device, compute_type)
    if key not in WHISPER_MODELS:
        WHISPER_MODELS[key] = WhisperModel(
            model_name,
            device=device,
            compute_type=compute_type,
        )

    return WHISPER_MODELS[key]


def transcribe_with_whisper(config):
    model_name = config.get("whisper_model", "small")
    device = config.get("whisper_device", "cuda")
    compute_type = config.get("whisper_compute_type", "float16")

    try:
        model = get_whisper_model(model_name, device, compute_type)
        segments, _ = model.transcribe(str(INPUT_FILE), language="pl")
    except Exception as e:
        print(f"Whisper nie zadziałał na {device}/{compute_type}: {e}")
        print("Próbuję fallback: cpu/int8...")
        model = get_whisper_model(model_name, "cpu", "int8")
        segments, _ = model.transcribe(str(INPUT_FILE), language="pl")

    return " ".join(segment.text.strip() for segment in segments).strip()


def listen_once(duration=None):
    try:
        import sounddevice as sd
        from scipy.io.wavfile import write

        config = load_config()
        microphone_device = config.get("microphone_device")
        record_seconds = duration or config.get("record_seconds", 7)

        recording = None
        used_sample_rate = None
        last_error = None

        for sample_rate in get_sample_rates(config):
            try:
                recording = record_audio(sd, sample_rate, microphone_device, record_seconds)
                used_sample_rate = sample_rate
                break
            except Exception as e:
                last_error = e

        if recording is None:
            print("Nie udało się nagrać audio z mikrofonu.")
            print("Uruchom: python mic_test.py i sprawdź poprawny numer mikrofonu.")
            if last_error:
                print("Ostatni błąd:", last_error)
            return None

        write(str(INPUT_FILE), used_sample_rate, recording)

        text = transcribe_with_whisper(config)
        if not text:
            print("Nie rozpoznano tekstu. Spróbuj powiedzieć coś głośniej albo sprawdź mikrofon.")
            return None

        return text

    except Exception as e:
        print("Błąd nagrywania lub rozpoznawania mowy:", e)
        print("Uruchom: python mic_test.py i sprawdź mikrofon oraz ustawienia w config.json.")

    return None
