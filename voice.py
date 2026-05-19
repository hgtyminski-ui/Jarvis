import asyncio
import hashlib
import re
import uuid
from pathlib import Path

from config import load_config


TTS_CACHE_DIR = Path(__file__).with_name("tts_cache")
MAX_SPEECH_CHARACTERS = 250
LONG_TEXT_SUFFIX = "Reszt\u0119 masz w terminalu."
QUOTE_CHARACTERS = "\"'\u201e\u201d\u00ab\u00bb`"
MARKDOWN_CHARACTERS = "*_#>|"
STANDALONE_PUNCTUATION = ".,;:!?-\u2013\u2014()[]{}"


def clean_text_for_speech(text):
    if not isinstance(text, str):
        text = str(text)

    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\.{2,}", ". ", text)
    text = text.translate(str.maketrans("", "", QUOTE_CHARACTERS + MARKDOWN_CHARACTERS))
    text = re.sub(r"[^\w\s.,;:!?()\-\u2013\u2014]", "", text, flags=re.UNICODE)

    tokens = []
    for token in text.split():
        if token.strip(STANDALONE_PUNCTUATION) == "":
            continue
        tokens.append(token)

    return " ".join(tokens)


def limit_text_for_speech(text):
    if len(text) <= MAX_SPEECH_CHARACTERS:
        return text

    shortened = text[:MAX_SPEECH_CHARACTERS]
    sentence_end = max(shortened.rfind("."), shortened.rfind("!"), shortened.rfind("?"))

    if sentence_end > 0:
        return shortened[: sentence_end + 1].strip()

    available_length = MAX_SPEECH_CHARACTERS - len(LONG_TEXT_SUFFIX) - 1
    shortened = shortened[:available_length].rsplit(" ", 1)[0].strip()
    return f"{shortened} {LONG_TEXT_SUFFIX}".strip()


def get_cache_file(text, config):
    cache_key = "|".join(
        [
            text,
            config.get("edge_voice", "pl-PL-MarekNeural"),
            config.get("edge_rate", "+0%"),
            config.get("edge_volume", "+0%"),
        ]
    )
    file_name = hashlib.sha256(cache_key.encode("utf-8")).hexdigest() + ".mp3"
    return TTS_CACHE_DIR / file_name


async def create_speech_file(text, config, output_file):
    import edge_tts

    communicate = edge_tts.Communicate(
        text=text,
        voice=config.get("edge_voice", "pl-PL-MarekNeural"),
        rate=config.get("edge_rate", "+0%"),
        volume=config.get("edge_volume", "+0%"),
    )
    await communicate.save(str(output_file))


def speak(text):
    config = load_config()
    if not config.get("voice_enabled", False):
        return False

    text = clean_text_for_speech(text)
    text = limit_text_for_speech(text)
    if not text:
        return False

    try:
        from playsound import playsound

        TTS_CACHE_DIR.mkdir(exist_ok=True)
        cache_file = get_cache_file(text, config)

        if not cache_file.exists():
            temporary_file = TTS_CACHE_DIR / f"{uuid.uuid4().hex}.tmp.mp3"
            try:
                asyncio.run(create_speech_file(text, config, temporary_file))
                temporary_file.replace(cache_file)
            finally:
                if temporary_file.exists():
                    temporary_file.unlink()

        playsound(str(cache_file))
    except Exception:
        return False

    return True
