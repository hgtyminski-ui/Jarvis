import pyttsx3


def main():
    engine = pyttsx3.init()
    voices = engine.getProperty("voices")

    for index, voice in enumerate(voices):
        print("index:", index)
        print("id:", voice.id)
        print("name:", voice.name)
        print("languages:", voice.languages)
        print()


if __name__ == "__main__":
    main()
