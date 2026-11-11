# The Qt interface runs inside the Engine process

The PySide6 tray, overlay and windows run on the Engine's main thread, replacing pystray; the Reader stays a supervised child process. A separate interface process talking to a headless Engine was rejected: it adds a message channel and a third process to supervise for no gain on a single-user desktop tool. Keyboard-hook and worker threads reach the interface only through Qt signals, never by touching widgets.

The standalone Dictation-only and Reader-only launchers are dropped at the same time: one entry point, with "Dictation on" and "Reader on" switches in the settings window.
