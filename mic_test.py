import sounddevice as sd


def main():
    print("Dostępne mikrofony:")

    devices = sd.query_devices()
    for index, device in enumerate(devices):
        if device.get("max_input_channels", 0) > 0:
            print(f"{index}: {device.get('name')} ({device.get('max_input_channels')} kanały)")

    print("Domyślne urządzenie:", sd.default.device)


if __name__ == "__main__":
    main()
