"""The microphone, picked by name.

The setting stores the microphone's name, not a number: Windows renumbers devices
when one is plugged in or out. A name that is not there falls back to the Windows
default for that recording, and the saved name is used again once the microphone returns.
"""


def input_names(devices) -> list[str]:
    """The names of the devices that can record, each once, in the order given
    (`devices` as sounddevice.query_devices() returns them)."""
    names = []
    for device in devices:
        if device["max_input_channels"] > 0 and device["name"] not in names:
            names.append(device["name"])
    return names


def resolve(name: str, devices, default_host_api: int | None = None) -> tuple[int | None, bool]:
    """(device index, fell_back). A blank name is the Windows default: (None, False).
    The same microphone is listed once per Windows audio system; the default one wins."""
    if not name:
        return None, False
    matches = [(i, d) for i, d in enumerate(devices)
               if d["max_input_channels"] > 0 and d["name"] == name]
    if not matches:
        return None, True
    for index, device in matches:
        if device.get("hostapi") == default_host_api:
            return index, False
    return matches[0][0], False
