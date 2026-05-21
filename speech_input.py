from pathlib import Path
import threading

from config import load_config


INPUT_FILE = Path(__file__).with_name("input.wav")
WHISPER_MODELS = {}
RECORDING_LOCK = threading.Lock()
RECORDING_STREAM = None
RECORDING_CHUNKS = []
RECORDING_CONFIG = None
RECORDING_SAMPLE_RATE = None


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


def start_recording():
    global RECORDING_STREAM, RECORDING_CHUNKS, RECORDING_CONFIG, RECORDING_SAMPLE_RATE

    try:
        import sounddevice as sd

        config = load_config()
        microphone_device = config.get("microphone_device")
        sample_rate = config.get("sample_rate", 48000)

        def audio_callback(indata, _frames, _time, _status):
            with RECORDING_LOCK:
                RECORDING_CHUNKS.append(indata.copy())

        with RECORDING_LOCK:
            if RECORDING_STREAM is not None:
                print("Nagrywanie juz trwa.")
                return False

            RECORDING_CHUNKS = []
            RECORDING_CONFIG = config
            RECORDING_SAMPLE_RATE = sample_rate

        stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            device=microphone_device,
            callback=audio_callback,
        )
        stream.start()

        with RECORDING_LOCK:
            RECORDING_STREAM = stream

        return True

    except Exception as e:
        with RECORDING_LOCK:
            RECORDING_STREAM = None
            RECORDING_CHUNKS = []
            RECORDING_CONFIG = None
            RECORDING_SAMPLE_RATE = None

        print("Blad rozpoczecia nagrywania:", e)
        print("Uruchom: python mic_test.py i sprawdz mikrofon oraz ustawienia w config.json.")
        return False


def stop_recording_and_transcribe():
    global RECORDING_STREAM, RECORDING_CHUNKS, RECORDING_CONFIG, RECORDING_SAMPLE_RATE

    try:
        import numpy as np
        from scipy.io.wavfile import write

        with RECORDING_LOCK:
            stream = RECORDING_STREAM

        if stream is None:
            return None

        stream.stop()
        stream.close()

        with RECORDING_LOCK:
            chunks = RECORDING_CHUNKS
            config = RECORDING_CONFIG or load_config()
            sample_rate = RECORDING_SAMPLE_RATE or config.get("sample_rate", 48000)
            RECORDING_STREAM = None
            RECORDING_CHUNKS = []
            RECORDING_CONFIG = None
            RECORDING_SAMPLE_RATE = None

        if not chunks:
            print("Nie rozpoznano mowy.")
            return None

        recording = np.concatenate(chunks, axis=0)
        write(str(INPUT_FILE), sample_rate, recording)

        text = transcribe_with_whisper(config)
        if not text:
            print("Nie rozpoznano mowy.")
            return None

        return text

    except Exception as e:
        with RECORDING_LOCK:
            RECORDING_STREAM = None
            RECORDING_CHUNKS = []
            RECORDING_CONFIG = None
            RECORDING_SAMPLE_RATE = None

        print("Blad nagrywania lub rozpoznawania mowy:", e)
        print("Uruchom: python mic_test.py i sprawdz mikrofon oraz ustawienia w config.json.")

    return None


def listen_once(duration=None):
    try:
        import sounddevice as sd
        from scipy.io.wavfile import write

        config = load_config()
        microphone_device = config.get("microphone_device")
        duration_seconds = duration or 7
        sample_rate = config.get("sample_rate", 48000)

        recording = record_audio(sd, sample_rate, microphone_device, duration_seconds)
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
