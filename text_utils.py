POLISH_CHARACTERS = str.maketrans(
    {
        "\u0105": "a",
        "\u0107": "c",
        "\u0119": "e",
        "\u0142": "l",
        "\u0144": "n",
        "\u00f3": "o",
        "\u015b": "s",
        "\u017a": "z",
        "\u017c": "z",
    }
)

PUNCTUATION_TO_REMOVE = str.maketrans("", "", ".,!?")


def normalize_text(text):
    text = str(text).lower()
    text = text.translate(POLISH_CHARACTERS)
    text = text.translate(PUNCTUATION_TO_REMOVE)
    return " ".join(text.split())
