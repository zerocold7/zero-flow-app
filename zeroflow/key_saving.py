"""Saving the AI Provider choice from the Settings window, and the API key.

The key goes to Windows Credential Manager under the provider's address and nowhere
else: not the settings file (storage.save refuses it too), not the log, not an error
message. It is written first: if Credential Manager fails, the settings file is left as
it was, so it never points at a key that was not saved.
"""
from zeroflow import credentials, storage


class KeyNotSaved(Exception):
    """Credential Manager refused. The message never contains the key."""


def save_provider(settings_path: str, store, provider: str, url: str, model: str,
                  key: str | None, clear_key: bool = False) -> None:
    """`key`: text to store; blank or None keeps what is stored. `clear_key` deletes it."""
    address = credentials.provider_address(provider, url)
    if address is not None:
        try:
            if key:
                store.set(address, key)
            elif clear_key:
                store.delete(address)
        except OSError as e:
            raise KeyNotSaved(f"Windows Credential Manager could not save the key for "
                              f"{address} (error {e.errno}). Nothing was changed.") from None
    storage.update(settings_path, {"AI_PROVIDER": provider, "AI_URL": url, "AI_MODEL": model})
