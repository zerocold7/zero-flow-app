"""API keys, kept in Windows Credential Manager — never in the settings file.

Each key is stored under its provider's address: the server alone (scheme, host and a
port that is not the default), so a changed path on the same server finds the same key.
The entry is a generic credential named "ZeroFlow:<address>".
"""
import sys
from urllib.parse import urlparse

PREFIX = "ZeroFlow:"
ANTHROPIC_ADDRESS = "https://api.anthropic.com"
_DEFAULT_PORTS = {"https": 443, "http": 80}


def address_of(url: str) -> str:
    """"https://API.example.com:8443/v1/chat" → "https://api.example.com:8443"."""
    parts = urlparse(url.strip())
    scheme = parts.scheme.lower()
    port = parts.port
    shown_port = f":{port}" if port and port != _DEFAULT_PORTS.get(scheme) else ""
    return f"{scheme}://{(parts.hostname or '').lower()}{shown_port}"


def provider_address(provider: str, ai_url: str) -> str | None:
    """The address a provider's key is stored under; None for one that takes no key."""
    if provider == "claude":
        return ANTHROPIC_ADDRESS
    if provider in ("openai", "custom"):
        return address_of(ai_url)
    return None


class MemoryStore:
    """A store that lives only in this process: the tests use it."""

    def __init__(self):
        self._keys = {}

    def get(self, address: str) -> str | None:
        return self._keys.get(address)

    def set(self, address: str, key: str) -> None:
        self._keys[address] = key

    def delete(self, address: str) -> None:
        self._keys.pop(address, None)

    def addresses(self) -> list[str]:
        return list(self._keys)


class WindowsStore:
    """Windows Credential Manager, through advapi32 (no extra package)."""

    _GENERIC = 1                # CRED_TYPE_GENERIC
    _LOCAL_MACHINE = 2          # CRED_PERSIST_LOCAL_MACHINE: this user, this PC
    _NOT_FOUND = 1168           # ERROR_NOT_FOUND

    def __init__(self):
        if sys.platform != "win32":
            self._api = None
            return
        import ctypes
        from ctypes import wintypes

        class CREDENTIAL(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD),
                        ("TargetName", wintypes.LPWSTR), ("Comment", wintypes.LPWSTR),
                        ("LastWritten", wintypes.FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD),
                        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD),
                        ("Attributes", ctypes.c_void_p), ("TargetAlias", wintypes.LPWSTR),
                        ("UserName", wintypes.LPWSTR)]

        api = ctypes.WinDLL("advapi32", use_last_error=True)
        api.CredReadW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                  ctypes.POINTER(ctypes.POINTER(CREDENTIAL))]
        api.CredReadW.restype = wintypes.BOOL
        api.CredWriteW.argtypes = [ctypes.POINTER(CREDENTIAL), wintypes.DWORD]
        api.CredWriteW.restype = wintypes.BOOL
        api.CredDeleteW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD]
        api.CredDeleteW.restype = wintypes.BOOL
        api.CredEnumerateW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(ctypes.POINTER(ctypes.POINTER(CREDENTIAL)))]
        api.CredEnumerateW.restype = wintypes.BOOL
        api.CredFree.argtypes = [ctypes.c_void_p]
        self._api, self._ctypes, self._CREDENTIAL = api, ctypes, CREDENTIAL
        self._DWORD = wintypes.DWORD

    def _fail(self, what: str):
        code = self._ctypes.get_last_error()
        raise OSError(code, f"Credential Manager could not {what} (error {code})")

    def get(self, address: str) -> str | None:
        if self._api is None:
            return None
        ctypes = self._ctypes
        found = ctypes.POINTER(self._CREDENTIAL)()
        if not self._api.CredReadW(PREFIX + address, self._GENERIC, 0, ctypes.byref(found)):
            if ctypes.get_last_error() == self._NOT_FOUND:
                return None
            self._fail("read a key")
        try:
            size = found.contents.CredentialBlobSize
            return ctypes.string_at(found.contents.CredentialBlob, size).decode("utf-16-le")
        finally:
            self._api.CredFree(found)

    def set(self, address: str, key: str) -> None:
        if self._api is None:
            raise OSError("Windows Credential Manager is only on Windows")
        ctypes = self._ctypes
        blob = key.encode("utf-16-le")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = self._CREDENTIAL(
            Type=self._GENERIC, TargetName=PREFIX + address, CredentialBlobSize=len(blob),
            CredentialBlob=ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)),
            Persist=self._LOCAL_MACHINE, UserName="Zero- Flow")
        if not self._api.CredWriteW(ctypes.byref(credential), 0):
            self._fail("save a key")

    def delete(self, address: str) -> None:
        if self._api is None:
            return
        if not self._api.CredDeleteW(PREFIX + address, self._GENERIC, 0):
            if self._ctypes.get_last_error() != self._NOT_FOUND:
                self._fail("delete a key")

    def addresses(self) -> list[str]:
        """The address of every key Zero- Flow saved (the "ZeroFlow:*" entries only)."""
        if self._api is None:
            return []
        ctypes = self._ctypes
        count = self._DWORD()
        found = ctypes.POINTER(ctypes.POINTER(self._CREDENTIAL))()
        if not self._api.CredEnumerateW(PREFIX + "*", 0, ctypes.byref(count), ctypes.byref(found)):
            if ctypes.get_last_error() == self._NOT_FOUND:
                return []
            self._fail("list the keys")
        try:
            names = [found[i].contents.TargetName for i in range(count.value)]
        finally:
            self._api.CredFree(found)
        return [name[len(PREFIX):] for name in names if name.startswith(PREFIX)]
