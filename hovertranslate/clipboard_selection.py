"""Asynchronous compatibility copy; only runs after an explicit selection hotkey."""
import time

from PySide6.QtCore import QMimeData, QObject, QTimer, Signal
from PySide6.QtWidgets import QApplication

from .selection import MAX_SELECTION
from .windows import clipboard_sequence, foreground_window, modifiers_released, send_copy


class ClipboardSelection(QObject):
    finished = Signal(int, str, str)  # job, selected text, user-facing error

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.poll)
        self.active = False
        self.snapshot = None
        self.copied_sequence = None

    def start(self, job, expected_window):
        self.cancel()
        self.job = job
        self.expected_window = expected_window
        self.phase = "release"
        self.deadline = time.monotonic()+3
        self.active = True
        self.timer.start()
        self.poll()

    def cancel(self):
        self.timer.stop()
        self.active = False
        if self.snapshot is not None and self.copied_sequence is not None:
            if clipboard_sequence() == self.copied_sequence:
                QApplication.clipboard().setMimeData(self.snapshot)
                self.snapshot = None
        self.snapshot = None
        self.copied_sequence = None

    def finish(self, text="", error=""):
        job = self.job
        self.cancel()
        self.finished.emit(job, text, error)

    def poll(self):
        if not self.active:
            return
        if foreground_window() != self.expected_window:
            self.finish(error="目标窗口已切换，请重新选中文字后再按快捷键。")
            return
        if time.monotonic() > self.deadline:
            self.finish(error="未读到选中文字，请确认文字已选中且应用允许复制，再试一次。")
            return
        clipboard = QApplication.clipboard()
        if self.phase == "release":
            if not modifiers_released():
                return
            # Take a deep copy because Qt owns and invalidates the original QMimeData.
            self.baseline = clipboard_sequence()
            self.snapshot = QMimeData()
            original = clipboard.mimeData()
            if original is not None:
                for format_name in original.formats():
                    self.snapshot.setData(format_name, original.data(format_name))
            if clipboard_sequence() != self.baseline:
                self.finish(error="剪贴板刚刚发生变化，请重新按快捷键。")
                return
            if foreground_window() != self.expected_window or not modifiers_released():
                self.finish(error="目标窗口或按键状态已变化，请松开按键后重试。")
                return
            self.phase = "copy"
            self.deadline = time.monotonic()+1.2
            try:
                send_copy()
            except OSError as exc:
                self.finish(error=str(exc))
        elif clipboard_sequence() != self.baseline:
            self.copied_sequence = clipboard_sequence()
            text = clipboard.text().strip()
            if clipboard_sequence() != self.copied_sequence:
                self.snapshot = None  # Never overwrite a newer clipboard update.
                self.finish(error="剪贴板已被其他操作更新，请重试。")
            elif len(text) > MAX_SELECTION:
                self.finish(error=f"选中文字超过 {MAX_SELECTION} 字，请缩小选择范围。")
            elif text:
                self.finish(text=text)
            else:
                self.finish(error="选中内容不是可复制的文字，请使用悬停识别。")
