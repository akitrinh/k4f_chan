"""Windows global hotkeys and a movable, capture-excluded translation chat."""

from __future__ import annotations

from collections import deque
import ctypes
from ctypes import wintypes
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication, QObject, QRect, Qt, QThread, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QSizeGrip, QVBoxLayout, QWidget


_WM_HOTKEY = 0x0312
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_NOREPEAT = 0x4000
_WDA_EXCLUDEFROMCAPTURE = 0x00000011


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", ctypes.c_size_t),
        ("lParam", ctypes.c_ssize_t),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
        ("lPrivate", wintypes.DWORD),
    ]


_user32 = None
if sys.platform == "win32":
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    _user32.RegisterHotKey.restype = wintypes.BOOL
    _user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.UnregisterHotKey.restype = wintypes.BOOL
    _user32.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    _user32.SetWindowDisplayAffinity.restype = wintypes.BOOL


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, owner: "Hotkeys") -> None:
        super().__init__()
        self.owner = owner

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) not in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            return False, 0
        msg = ctypes.cast(int(message), ctypes.POINTER(_MSG)).contents
        if msg.message != _WM_HOTKEY:
            return False, 0
        signal = self.owner._registered.get(int(msg.wParam))
        if signal is None:
            return False, 0
        signal.emit()
        return True, 0


class Hotkeys(QObject):
    """Register thread hotkeys on the Qt GUI thread, without keyboard hooks.

    Call start() and close() on the GUI thread. Registration failures are
    independent: an occupied shortcut does not disable the other shortcut.
    """

    toggle_requested = Signal()
    mode_requested = Signal()
    _next_id = 0x4E10

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._filter = _HotkeyFilter(self)
        self._registered: dict[int, object] = {}
        self._app: QCoreApplication | None = None
        self._started = False
        self._warnings: list[str] = []

    def start(self) -> list[str]:
        if self._started:
            return list(self._warnings)
        app = QCoreApplication.instance()
        if app is None or QThread.currentThread() != app.thread():
            return ["Global hotkeys must be started on the Qt application thread."]
        if _user32 is None:
            return ["Global hotkeys are available only on Windows."]
        self._app = app
        self._started = True
        self._warnings = []
        app.installNativeEventFilter(self._filter)
        app.aboutToQuit.connect(self.close)
        for key, name, signal in (
            (ord("T"), "Ctrl+Alt+T", self.toggle_requested),
            (ord("F"), "Ctrl+Alt+F", self.mode_requested),
        ):
            identifier = Hotkeys._next_id
            Hotkeys._next_id += 1
            if identifier > 0xBFFF:
                self._warnings.append(f"Could not register {name}: application hotkey IDs exhausted.")
                continue
            if _user32.RegisterHotKey(None, identifier, _MOD_CONTROL | _MOD_ALT | _MOD_NOREPEAT, key):
                self._registered[identifier] = signal
            else:
                code = ctypes.get_last_error()
                self._warnings.append(
                    f"Could not register {name} (Windows error {code}); another application may use it. "
                    "Use the buttons in this window instead."
                )
        return list(self._warnings)

    def close(self) -> None:
        if not self._started:
            return
        if self._app is not None and QThread.currentThread() != self._app.thread():
            raise RuntimeError("Hotkeys.close() must run on the Qt application thread.")
        if _user32 is not None:
            for identifier in self._registered:
                _user32.UnregisterHotKey(None, identifier)
        self._registered.clear()
        if self._app is not None:
            self._app.removeNativeEventFilter(self._filter)
            try:
                self._app.aboutToQuit.disconnect(self.close)
            except (RuntimeError, TypeError):
                pass
        self._app = None
        self._started = False


def set_capture_excluded(widget: QWidget, excluded: bool) -> bool:
    """Set capture visibility of an owned top-level HWND after showing it.

    True excludes the window on Windows 10 2004+; False restores normal
    screenshot visibility. Failure must be reported, not treated as protection.
    This is not a security or DRM boundary.
    """
    if _user32 is None or not widget.isWindow():
        return False
    if excluded and sys.getwindowsversion().build < 19041:
        return False
    affinity = _WDA_EXCLUDEFROMCAPTURE if excluded else 0
    return bool(_user32.SetWindowDisplayAffinity(wintypes.HWND(int(widget.winId())), affinity))


class TranslationChatPanel(QWidget):
    """Session-only dialogue history in the right black side area.

    Native window chrome provides dragging/resizing. New translations never
    reposition the panel, steal focus, or erase older messages. Only geometry
    is persisted by the owning application, never the translated content.
    """

    geometry_changed = Signal()
    dismissed = Signal()

    def __init__(
        self, parent: QWidget | None = None, *,
        title: str = "k4f_chan · Lịch sử dịch",
        accessible_name: str = "Lịch sử dịch NIKKE",
        history_accessible_name: str = "Các tin nhắn đã dịch",
    ) -> None:
        super().__init__(
            parent,
            Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTitleHint
            | Qt.WindowType.WindowSystemMenuHint
            | Qt.WindowType.WindowCloseButtonHint,
        )
        # Opaque native windows support Windows 10 capture exclusion, unlike
        # per-pixel translucent overlays. Mouse input stays inside this window.
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setWindowTitle(title)
        self.setAccessibleName(accessible_name)
        self.setMinimumSize(220, 220)
        self.setStyleSheet("TranslationChatPanel { background: #05080D; color: #EFF5FC; }")
        self._screen = QRect()
        self._placed = False
        self._messages: deque[str] = deque(maxlen=50)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 5)
        layout.setSpacing(7)
        heading = QLabel("ANH → VIỆT  /  LỊCH SỬ", self)
        heading.setStyleSheet("color: #79E7CC; font-size: 10px; font-weight: 700; background: transparent;")
        layout.addWidget(heading)
        self.history_view = QPlainTextEdit(self)
        self.history_view.setReadOnly(True)
        self.history_view.setAccessibleName(history_accessible_name)
        self.history_view.setPlaceholderText(
            "Bản dịch sẽ xuất hiện ở đây.\n\n"
            "Các câu trước được giữ lại để cuộn đọc.\n\n"
            "Kéo thanh tiêu đề để di chuyển; kéo cạnh hoặc góc dưới để đổi kích cỡ."
        )
        self.history_view.setStyleSheet(
            "QPlainTextEdit { background: #05080D; color: #EFF5FC; border: none;"
            " font-family: 'Segoe UI'; font-size: 17px; padding: 2px; }"
        )
        self.history_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.history_view, 1)
        footer = QHBoxLayout()
        hint = QLabel("Cuộn để xem câu trước", self)
        hint.setStyleSheet("color: #7E91A8; font-size: 10px; background: transparent;")
        footer.addWidget(hint)
        footer.addStretch()
        footer.addWidget(QSizeGrip(self))
        layout.addLayout(footer)

    def set_subtitle(self, text: str) -> None:
        text = text.strip()
        if not text or (self._messages and text == self._messages[-1]):
            return
        scrollbar = self.history_view.verticalScrollBar()
        previous_scroll = scrollbar.value()
        following_latest = previous_scroll >= scrollbar.maximum() - 2
        trimmed = len(self._messages) == self._messages.maxlen
        self._messages.append(text)
        if trimmed:
            self.history_view.setPlainText("\n\n".join(self._messages))
        else:
            self.history_view.appendPlainText(("\n" if len(self._messages) > 1 else "") + text)
        if following_latest:
            scrollbar.setValue(scrollbar.maximum())
        else:
            scrollbar.setValue(previous_scroll)

    def place_on(self, screen_geometry: QRect, *, reset: bool = False) -> None:
        if self._placed and self._screen == screen_geometry and not reset:
            return
        self._screen = QRect(screen_geometry)
        screen = self._screen
        width = min(360, max(240, round(screen.width() * 0.22)), screen.width() - 32)
        height = min(520, max(240, round(screen.height() * 0.60)), screen.height() - 80)
        self._placed = True
        self.setGeometry(
            screen.x() + screen.width() - width - 16,
            screen.y() + max(48, round(screen.height() * 0.12)),
            width, height,
        )

    def restore_placement(self, value: object) -> None:
        if (not isinstance(value, list) or len(value) != 4
                or not all(type(item) is int for item in value)
                or value[2] < 220 or value[3] < 220 or self._screen.isEmpty()):
            return
        screen = self._screen
        width = min(value[2], screen.width() - 32)
        height = min(value[3], screen.height() - 80)
        x = max(screen.x() + 12, min(value[0], screen.right() - width - 12))
        y = max(screen.y() + 36, min(value[1], screen.bottom() - height - 16))
        self._placed = True
        self.setGeometry(x, y, width, height)

    def moveEvent(self, event) -> None:
        super().moveEvent(event)
        if self._placed:
            self.geometry_changed.emit()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._placed:
            self.geometry_changed.emit()

    def closeEvent(self, event) -> None:
        self.dismissed.emit()
        event.accept()
