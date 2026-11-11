"""The microphone, and the Reader's output, picked by name.

The setting stores the device's name, not a number: Windows renumbers devices when one
is plugged in or out. A name that is not there falls back to the Windows default for
that recording (or that run of the Reader), and the saved name is used again once the
device returns.
"""


def _channels(output: bool) -> str:
    return "max_output_channels" if output else "max_input_channels"


def input_names(devices) -> list[str]:
    """The names of the devices that can record, each once, in the order given
    (`devices` as sounddevice.query_devices() returns them)."""
    return _names(devices, output=False)


def output_names(devices) -> list[str]:
    """The names of the devices that can play, each once, in the order given."""
    return _names(devices, output=True)


def _names(devices, output: bool) -> list[str]:
    channels, names = _channels(output), []
    for device in devices:
        if device.get(channels, 0) > 0 and device["name"] not in names:
            names.append(device["name"])
    return names


def resolve(name: str, devices, default_host_api: int | None = None,
            output: bool = False) -> tuple[int | None, bool]:
    """(device index, fell_back). A blank name is the Windows default: (None, False).
    The same device is listed once per Windows audio system; the default one wins.
    `output`: look among the devices that play, not those that record."""
    if not name:
        return None, False
    channels = _channels(output)
    matches = [(i, d) for i, d in enumerate(devices)
               if d.get(channels, 0) > 0 and d["name"] == name]
    if not matches:
        return None, True
    for index, device in matches:
        if device.get("hostapi") == default_host_api:
            return index, False
    return matches[0][0], False
