"""The overlay: a small pill at the bottom centre of the screen that shows what the
Engine is doing (Recording with a level meter, Transcribing, AI, Reading).

It must never take focus: dictation types into another program, and a window that
stole focus would receive the words itself. So it is a tool window that does not accept
focus, is not activated when shown, and lets clicks pass through. A test enforces this
(tests/test_window_overlay.py) and a mutation guard breaks it on purpose.

Hook and worker threads never touch widgets (ADR 0001): they emit the signals of
`UiBridge`, which Qt delivers on the main thread.
"""
from PySide6.QtCore import QObject, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QApplication, QWidget

STATES = ("recording", "transcribing", "ai", "reading")
LABELS = {"recording": "Recording", "transcribing": "Transcribing", "ai": "AI", "reading": "Reading"}
COLOURS = {"recording": "#e5484d", "transcribing": "#f5a524", "ai": "#8e4ec6", "reading": "#30a46c"}
WIDTH, HEIGHT, BOTTOM_GAP = 260, 40, 56


class UiBridge(QObject):
    """What other threads use to reach the interface."""
    status = Signal(str)          # one of STATES
    level = Signal(float)         # microphone level, 0 to 1
    cleared = Signal()            # nothing to show
    problem = Signal(str, str)    # a toast: title, text
    booted = Signal()             # the Engine finished starting
    detail = Signal(str)          # what is recording: the Mode, e.g. "Arabic · Polish"


class Overlay(QWidget):
    def __init__(self):
        super().__init__(None, Qt.ToolTip | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.resize(WIDTH, HEIGHT)
        self.state = None
        self.level = 0.0
        self.detail = ""

    def show_state(self, state: str, level: float = 0.0) -> None:
        if state not in STATES:
            raise ValueError(f"{state!r} is not one of {STATES}")
        self.state = state
        self.set_level(level)
        self._place()
        self.show()
        self.update()

    def set_level(self, level: float) -> None:
        self.level = min(1.0, max(0.0, float(level)))
        self.update()

    def set_detail(self, text: str) -> None:
        self.detail = text
        self.update()

    def hide_overlay(self) -> None:
        self.state = None
        self.detail = ""
        self.hide()

    def _place(self) -> None:
        area = (self.screen() or QApplication.primaryScreen()).availableGeometry()
        self.move(area.center().x() - WIDTH // 2, area.bottom() - HEIGHT - BOTTOM_GAP)

    def paintEvent(self, _event) -> None:
        if self.state is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(24, 24, 27, 225))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRectF(0, 0, WIDTH, HEIGHT), HEIGHT / 2, HEIGHT / 2)
        painter.setBrush(QColor(COLOURS[self.state]))
        painter.drawEllipse(QRectF(16, HEIGHT / 2 - 5, 10, 10))
        painter.setPen(QColor("white"))
        painter.setFont(QFont("Segoe UI", 10))
        shown = LABELS[self.state]
        if self.state == "recording" and self.detail:
            shown += f" · {self.detail}"
        painter.drawText(QRectF(34, 0, WIDTH - 90, HEIGHT), Qt.AlignVCenter, shown)
        if self.state == "recording":
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(255, 255, 255, 60))
            painter.drawRoundedRect(QRectF(WIDTH - 56, HEIGHT / 2 - 3, 44, 6), 3, 3)
            painter.setBrush(QColor(COLOURS["recording"]))
            painter.drawRoundedRect(QRectF(WIDTH - 56, HEIGHT / 2 - 3, 44 * self.level, 6), 3, 3)
