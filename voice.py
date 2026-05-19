import re

from config import load_config


QUOTE_CHARACTERS = "\"'\u201e\u201d\u00ab\u00bb`"
MARKDOWN_CHARACTERS = "*_#>|"
STANDALONE_PUNCTUATION = ".,;:!?-\u2013\u2014()[]{}"


def clean_text_for_speech(text):
    if not isinstance(text, str):
        text = str(text)

    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\.{2,}", ". ", text)
    text = text.translate(str.maketrans("", "", QUOTE_CHARACTERS + MARKDOWN_CHARACTERS))

    tokens = []
    for token in text.split():
        if token.strip(STANDALONE_PUNCTUATION) == "":
            continue
        tokens.append(token)

    return " ".join(tokens)


def speak(text):
    if not text:
        return False

    text = clean_text_for_speech(text)
    if not text:
        return False

    try:
        import pyttsx3

        config = load_config()
        if not config.get("voice_enabled", False):
            return False

        engine = pyttsx3.init()
        voice_rate = config.get("voice_rate", 150)
        voice_volume = config.get("voice_volume", 0.9)
        voice_id = config.get("voice_id", 0)

        engine.setProperty("rate", voice_rate)
        engine.setProperty("volume", voice_volume)

        voices = engine.getProperty("voices")
        if isinstance(voice_id, int) and 0 <= voice_id < len(voices):
            engine.setProperty("voice", voices[voice_id].id)

        engine.say(text)
        engine.runAndWait()
    except Exception:
        return False

    return True
