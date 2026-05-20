from pathlib import Path

from config import load_config


INPUT_FILE = Path(__file__).with_name("input.wav")
WHISPER_MODELS = {}


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
    model_name = config.get("whisper_model", "base")
    device = config.get("whisper_device", "cpu")
    compute_type = config.get("whisper_compute_type", "int8")

    model = get_whisper_model(model_name, device, compute_type)
    segments, _ = model.transcribe(
        str(INPUT_FILE),
        language="pl",
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
    )

    text = " ".join(segment.text.strip() for segment in segments)
    return " ".join(text.split())


def listen_once(duration=None):
    try:
        import sounddevice as sd
        from scipy.io.wavfile import write

        config = load_config()
        microphone_device = config.get("microphone_device")
        record_seconds = duration or config.get("record_seconds", 7)
        sample_rate = config.get("sample_rate", 48000)

        recording = record_audio(sd, sample_rate, microphone_device, record_seconds)
        if recording is None:
            print("Nie udalo sie nagrac audio z mikrofonu.")
            print("Uruchom: python mic_test.py i sprawdz poprawny numer mikrofonu.")
            return None

        write(str(INPUT_FILE), sample_rate, recording)

        text = transcribe_with_whisper(config)
        if not text:
            print("Nie rozpoznano mowy.")
            return None

        return text

    except Exception as e:
        print("Blad nagrywania lub rozpoznawania mowy:", e)
        print("Uruchom: python mic_test.py i sprawdz mikrofon oraz ustawienia w config.json.")

    return None
