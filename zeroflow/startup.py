"""Start with Windows: the HKCU Run key, not the settings file.

Its own module, with nothing but winreg, so the uninstaller (zeroflow/uninstall.py) can
remove the entry without loading Qt or the settings.
"""


class StartupKey:
    RUN = r"Software\Microsoft\Windows\CurrentVersion\Run"
    NAME = "ZeroFlow"

    def __init__(self, command: str):
        self.command = command

    def get(self) -> bool:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN) as key:
                winreg.QueryValueEx(key, self.NAME)
            return True
        except OSError:
            return False

    def set(self, on: bool) -> None:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.RUN, 0, winreg.KEY_SET_VALUE) as key:
            if on:
                winreg.SetValueEx(key, self.NAME, 0, winreg.REG_SZ, self.command)
            else:
                try:
                    winreg.DeleteValue(key, self.NAME)
                except OSError:
                    pass
