from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import logging
import os
import sys
import threading
import time

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, QObject, Signal, Slot, QLockFile
from PySide6.QtGui import QColor, QCursor, QFont, QIcon, QPainter, QPen, QPixmap, QAction
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSpinBox,
    QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
)

from .core import (Cancelled, Rect, Settings, UserError, load_settings, popup_position,
                   save_settings, settings_path, stream_translation)
from .recognition import Recognizer
from .selection import read_selected_text
from .clipboard_selection import ClipboardSelection
from .windows import (cursor_and_monitor, pressed, shortcut_down, selection_shortcut_down,
                      foreground_window, foreground_process, modifiers_released)


STYLE = """
QWidget { font-family: 'Microsoft YaHei UI', 'Segoe UI'; font-size: 13px; color: #24324a; }
QMainWindow, QWidget#page { background: #f4f6fb; }
QFrame#card { background: white; border: 1px solid #e3e8f2; border-radius: 14px; }
QLabel#eyebrow { color: #6676b8; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
QLabel#title { font-size: 27px; font-weight: 700; color: #17233d; }
QLabel#muted { color: #72809a; }
QLabel#status { background: #eaf0ff; color: #4561b6; border-radius: 8px; padding: 9px 12px; }
QLineEdit, QComboBox, QSpinBox { background: #f8faff; border: 1px solid #dce3f0;
    border-radius: 7px; min-height: 30px; padding: 3px 9px; selection-background-color: #6478dc; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #6b7cda; }
QPushButton { background: #eef2fb; border: 0; border-radius: 7px; padding: 9px 16px; }
QPushButton:hover { background: #e1e8fa; }
QPushButton#primary { background: #586bd5; color: white; font-weight: 600; }
QPushButton#primary:hover { background: #485cc6; }
QPushButton:disabled { background: #e7eaf2; color: #9aa4b6; }
QTextEdit { background: #f7f9fe; border: 1px solid #e7ecf5; border-radius: 8px; padding: 8px; }
QCheckBox { spacing: 8px; }
QScrollArea { border: none; background: transparent; }
"""


def icon():
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#586bd5"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 60, 60, 17, 17)
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Microsoft YaHei UI", 29, QFont.Weight.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, "译")
    painter.end()
    return QIcon(pixmap)


def label(text, name=None):
    widget = QLabel(text)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


class SelectionOutline(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor("#7d8eea"), 2))
        p.setBrush(QColor(102, 124, 230, 18))
        p.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 4, 4)


class TranslationPopup(QWidget):
    dismissed = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("HoverTranslate · 翻译")
        self.setObjectName("popup")
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet(STYLE + "QWidget#popup {background: white; border: 1px solid #dce2f0; border-radius: 12px;}")
        self.anchor = QPoint()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)
        row = QHBoxLayout()
        row.addWidget(label("HOVER / TRANSLATE", "eyebrow"))
        row.addStretch()
        self.pin = QPushButton("固定")
        self.pin.setCheckable(True)
        self.pin.setToolTip("固定后移动鼠标不会关闭，Esc 仍可关闭")
        row.addWidget(self.pin)
        close = QPushButton("×")
        close.setFixedWidth(32)
        close.clicked.connect(self.dismissed.emit)
        row.addWidget(close)
        layout.addLayout(row)
        self.status = label("正在识别屏幕文字…", "muted")
        layout.addWidget(self.status)
        self.source = QTextEdit()
        self.source.setReadOnly(True)
        self.source.setMaximumHeight(90)
        self.source.setPlaceholderText("鼠标附近的原文")
        layout.addWidget(self.source)
        self.translation = QTextEdit()
        self.translation.setReadOnly(True)
        self.translation.setPlaceholderText("译文会在这里逐字显示")
        self.translation.setMinimumHeight(95)
        layout.addWidget(self.translation)
        footer = QHBoxLayout()
        footer.addWidget(label("本机识别 · 仅文字发送至 API", "muted"))
        footer.addStretch()
        self.copy = QPushButton("复制译文")
        self.copy.setEnabled(False)
        self.copy.clicked.connect(lambda: QApplication.clipboard().setText(self.translation.toPlainText()))
        footer.addWidget(self.copy)
        layout.addLayout(footer)

    def start(self, anchor):
        self.anchor = QPoint(anchor)
        self.pin.setChecked(False)
        self.source.clear()
        self.translation.clear()
        self.copy.setEnabled(False)
        self.status.setText("正在识别屏幕文字…")
        screen = QApplication.screenAt(anchor) or QApplication.primaryScreen()
        work = screen.availableGeometry()
        self.setFixedSize(min(430, max(240, work.width()-20)), min(330, max(220, work.height()-20)))
        self.reposition()
        self.show()

    def reposition(self):
        screen = QApplication.screenAt(self.anchor) or QApplication.primaryScreen()
        work = screen.availableGeometry()
        x, y = popup_position(self.anchor.x(), self.anchor.y(), self.width(), self.height(),
                              Rect(work.x(), work.y(), work.width(), work.height()))
        self.move(x, y)


class SettingsWindow(QMainWindow):
    def __init__(self, controller):
        super().__init__()
        self.controller = controller
        self.setWindowTitle("HoverTranslate · 悬停翻译设置")
        self.setWindowIcon(icon())
        self.resize(670, 860)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        page.setObjectName("page")
        root = QVBoxLayout(page)
        root.setContentsMargins(30, 26, 30, 26)
        root.setSpacing(18)
        root.addWidget(label("A LITTLE CLOSER TO UNDERSTANDING", "eyebrow"))
        root.addWidget(label("指尖一停，译文即现。", "title"))
        root.addWidget(label("悬停取词，或选中文字后按快捷键。译文显示在鼠标附近。", "muted"))
        self.state = label("正在准备本机文字识别引擎…", "status")
        root.addWidget(self.state)
        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(22, 19, 22, 19)
        form.setSpacing(12)
        form.addRow(label("01  /  翻译服务", "eyebrow"))
        self.provider = QComboBox()
        self.provider.addItems(["DeepSeek", "自定义兼容接口", "Ollama（本机）"])
        form.addRow("服务预设", self.provider)
        self.url = QLineEdit()
        self.url.setPlaceholderText("https://你的服务地址/v1")
        form.addRow("Base URL", self.url)
        self.model = QLineEdit()
        self.model.setPlaceholderText("例如 deepseek-chat")
        form.addRow("模型名称", self.model)
        keyrow = QHBoxLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("填写服务商的 API Key")
        keyrow.addWidget(self.key)
        reveal = QCheckBox("显示")
        reveal.toggled.connect(lambda value: self.key.setEchoMode(
            QLineEdit.EchoMode.Normal if value else QLineEdit.EchoMode.Password))
        keyrow.addWidget(reveal)
        form.addRow("API Key", keyrow)
        self.target = QComboBox()
        self.target.setEditable(True)
        self.target.addItems(["简体中文", "繁體中文", "English", "日本語", "한국어", "Français", "Deutsch"])
        form.addRow("译为", self.target)
        root.addWidget(card)
        interaction = QFrame()
        interaction.setObjectName("card")
        form2 = QFormLayout(interaction)
        form2.setContentsMargins(22, 19, 22, 19)
        form2.setSpacing(12)
        form2.addRow(label("02  /  触发方式与取词", "eyebrow"))
        self.trigger = QComboBox()
        self.trigger.addItems(["两种方式同时启用", "仅悬停 + 快捷键", "仅选中 + 快捷键"])
        form2.addRow("翻译方式", self.trigger)
        self.hotkey = QComboBox()
        self.hotkey.addItems(["Ctrl + Alt", "Ctrl + Shift", "Alt + Shift"])
        form2.addRow("悬停快捷键（按住）", self.hotkey)
        self.selected_hotkey = QComboBox()
        self.selected_hotkey.addItems(["Ctrl + Shift + F8", "Ctrl + Alt + T", "Alt + F8"])
        form2.addRow("选中快捷键（按一次）", self.selected_hotkey)
        self.copy_fallback = QCheckBox("直接读取失败时临时复制，完成后恢复剪贴板")
        form2.addRow("兼容取词", self.copy_fallback)
        self.delay = QSpinBox()
        self.delay.setRange(250, 2000)
        self.delay.setSingleStep(50)
        self.delay.setSuffix(" ms")
        form2.addRow("鼠标停留", self.delay)
        self.mode = QComboBox()
        self.mode.addItems(["鼠标所在行", "附近段落（最多 8 行）"])
        form2.addRow("自动框选", self.mode)
        self.width = QSpinBox()
        self.width.setRange(400, 1600)
        self.width.setSingleStep(100)
        self.width.setSuffix(" px")
        form2.addRow("识别区域宽度", self.width)
        self.height = QSpinBox()
        self.height.setRange(120, 600)
        self.height.setSingleStep(20)
        self.height.setSuffix(" px")
        form2.addRow("识别区域高度", self.height)
        self.trigger.currentIndexChanged.connect(self.update_trigger_controls)
        root.addWidget(interaction)
        row = QHBoxLayout()
        self.test = QPushButton("测试 API")
        self.test.clicked.connect(controller.test_api)
        row.addWidget(self.test)
        preview = QPushButton("预览浮窗")
        preview.clicked.connect(controller.preview)
        row.addWidget(preview)
        row.addStretch()
        self.save = QPushButton("保存并启用")
        self.save.setObjectName("primary")
        self.save.clicked.connect(controller.save)
        row.addWidget(self.save)
        root.addWidget(label("使用提示：松开快捷键后可移入浮窗复制译文；移远自动收起，Esc 关闭。\n"
                             "关闭设置窗口后继续在托盘运行。API Key 使用 Windows DPAPI 加密保存。", "muted"))
        root.addStretch()
        scroll.setWidget(page)
        shell = QWidget()
        outer = QVBoxLayout(shell)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll, 1)
        footer = QWidget()
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(30, 12, 30, 18)
        footer_layout.addLayout(row)
        outer.addWidget(footer)
        self.setCentralWidget(shell)
        self.fill(controller.settings)
        self.provider.currentIndexChanged.connect(self.preset)

    def fill(self, settings):
        self.url.setText(settings.base_url)
        self.model.setText(settings.model)
        self.key.setText(settings.api_key)
        self.target.setCurrentText(settings.target)
        self.hotkey.setCurrentText(settings.hotkey)
        self.delay.setValue(settings.delay_ms)
        self.mode.setCurrentIndex(0 if settings.selection == "line" else 1)
        self.width.setValue(settings.capture_width)
        self.height.setValue(settings.capture_height)
        self.trigger.setCurrentIndex({"both": 0, "hover": 1, "selected": 2}[settings.trigger_mode])
        self.selected_hotkey.setCurrentText(settings.selection_hotkey)
        self.copy_fallback.setChecked(settings.copy_fallback)
        self.update_trigger_controls()
        self.provider.setCurrentIndex(0 if settings.base_url == "https://api.deepseek.com" else
                                      2 if "localhost" in settings.base_url else 1)

    def preset(self, index):
        if index == 0:
            self.url.setText("https://api.deepseek.com")
            self.model.setText("deepseek-chat")
        elif index == 2:
            self.url.setText("http://localhost:11434/v1")
            self.model.setText("qwen2.5:7b")
        # Never silently reuse a provider's key on a different destination.
        self.key.clear()

    def read(self):
        return Settings(base_url=self.url.text().strip(), model=self.model.text().strip(),
                        target=self.target.currentText().strip(), hotkey=self.hotkey.currentText(),
                        delay_ms=self.delay.value(), selection="line" if self.mode.currentIndex() == 0 else "paragraph",
                        capture_width=self.width.value(), capture_height=self.height.value(), api_key=self.key.text().strip(),
                        trigger_mode=("both", "hover", "selected")[self.trigger.currentIndex()],
                        selection_hotkey=self.selected_hotkey.currentText(), copy_fallback=self.copy_fallback.isChecked())

    def update_trigger_controls(self):
        hover = self.trigger.currentIndex() != 2
        for widget in (self.hotkey, self.delay, self.mode, self.width, self.height):
            widget.setEnabled(hover)
        selected = self.trigger.currentIndex() != 1
        self.selected_hotkey.setEnabled(selected)
        self.copy_fallback.setEnabled(selected)

    def closeEvent(self, event):
        if self.controller.tray.isVisible():
            event.ignore()
            self.hide()
            if not self.controller.close_tip:
                self.controller.tray.showMessage("HoverTranslate", "已在托盘运行。双击图标打开设置，右键可退出。")
                self.controller.close_tip = True
        else:
            self.controller.quit()


class Events(QObject):
    ready = Signal(str)
    source = Signal(int, str, object)
    chunk = Signal(int, str)
    result = Signal(int, str, bool)
    test_result = Signal(str)
    selection_result = Signal(int, str, str)


class Controller(QObject):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.startup_error = ""
        try:
            self.settings = load_settings()
        except UserError as exc:
            self.settings = Settings()
            self.startup_error = str(exc)
        self.enabled = True
        self.ready = False
        self.close_tip = False
        self.sequence = 0
        self.cancel = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="hover-ocr")
        self.test_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="api-test")
        self.selection_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="selection-reader")
        self.future = None
        self.testing = False
        self.test_cancel = threading.Event()
        self.recognizer = None
        self.cache = OrderedDict()
        self.cache_lock = threading.Lock()
        self.events = Events()
        queued = Qt.ConnectionType.QueuedConnection
        self.events.ready.connect(self.on_ready, queued)
        self.events.source.connect(self.on_source, queued)
        self.events.chunk.connect(self.on_chunk, queued)
        self.events.result.connect(self.on_result, queued)
        self.events.test_result.connect(self.on_test_result, queued)
        self.events.selection_result.connect(self.on_selection_result, queued)
        self.selection_reader = ClipboardSelection(self)
        self.selection_reader.finished.connect(self.on_clipboard_selection)
        self.was_selected_down = False
        self.suppress_hover = False
        self.selection_future = None
        self.popup = TranslationPopup()
        self.popup.dismissed.connect(self.dismiss)
        self.outline = SelectionOutline()
        self.window = SettingsWindow(self)
        self.tray = QSystemTrayIcon(icon(), self)
        self.tray.setToolTip("HoverTranslate · " + self.trigger_description())
        menu = QMenu()
        show = menu.addAction("打开设置")
        show.triggered.connect(self.show_settings)
        self.pause_action = QAction("暂停翻译快捷键", self)
        self.pause_action.setCheckable(True)
        self.pause_action.toggled.connect(self.pause)
        menu.addAction(self.pause_action)
        menu.addSeparator()
        menu.addAction("退出").triggered.connect(self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_settings()
                                    if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        self.last_position = QCursor.pos()
        self.stable_since = time.monotonic()
        self.was_down = False
        self.attempted = None
        self.hide_since = None
        self.active_job = False
        self.source_region = None
        self.tick = QTimer(self)
        self.tick.timeout.connect(self.poll)
        self.tick.start(45)
        self.executor.submit(self.prepare)

    def prepare(self):
        try:
            self.recognizer = Recognizer()
            self.events.ready.emit("")
        except Exception:
            logging.exception("OCR initialization failed")
            self.events.ready.emit("文字识别引擎未能启动，请检查程序文件是否完整。")

    @Slot(str)
    def on_ready(self, error):
        self.ready = not error
        self.window.state.setText(error or self.startup_error or
                                 "已就绪 · " + self.trigger_description())

    def trigger_description(self):
        values = []
        if self.settings.trigger_mode in ("both", "hover"):
            values.append("悬停 " + self.settings.hotkey)
        if self.settings.trigger_mode in ("both", "selected"):
            values.append("选中 " + self.settings.selection_hotkey)
        return " / ".join(values)

    def show_settings(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def save(self):
        try:
            settings = self.window.read()
            save_settings(settings)
        except (UserError, OSError) as exc:
            QMessageBox.warning(self.window, "无法保存", str(exc))
            return
        self.dismiss()
        self.settings = settings
        with self.cache_lock:
            self.cache.clear()
        self.startup_error = ""
        self.pause_action.setChecked(False)
        self.enabled = True
        self.tray.setToolTip("HoverTranslate · " + self.trigger_description())
        self.window.state.setText("已保存并启用 · " + self.trigger_description())

    def pause(self, paused):
        self.enabled = not paused
        self.dismiss()
        self.window.state.setText("翻译快捷键已暂停" if paused else "翻译快捷键已启用")

    def dismiss(self):
        self.cancel.set()
        self.selection_reader.cancel()
        self.sequence += 1
        if self.future:
            self.future.cancel()
        if self.selection_future:
            self.selection_future.cancel()
        self.popup.hide()
        self.popup.pin.setChecked(False)
        self.outline.hide()
        self.hide_since = None
        self.active_job = False
        self.source_region = None

    def update_visibility(self, point, now):
        """Keep the source and popup interactive, with a short grace period across their gap."""
        visible = self.popup.isVisible()
        if not self.active_job and not visible:
            return
        if visible and self.popup.pin.isChecked():
            self.hide_since = None
            return
        anchor = self.job_anchor if self.active_job else self.popup.anchor
        source = self.source_region or QRect(anchor.x()-12, anchor.y()-12, 24, 24)
        in_source = source.adjusted(-5, -5, 5, 5).contains(point)
        in_popup = visible and self.popup.geometry().adjusted(-3, -3, 3, 3).contains(point)
        if in_source or in_popup:
            self.hide_since = None
        elif self.hide_since is None:
            self.hide_since = now
        elif now-self.hide_since >= .18:
            # Invalidate pending results too, so a slow response cannot reopen the dismissed popup.
            self.dismiss()

    def poll(self):
        point = QCursor.pos()
        now = time.monotonic()
        selected_down = selection_shortcut_down(self.settings.selection_hotkey)
        selected_edge = selected_down and not self.was_selected_down
        self.was_selected_down = selected_down
        if pressed(0x1B):
            self.dismiss()
            return
        self.update_visibility(point, now)
        if self.enabled and self.settings.trigger_mode in ("both", "selected") and selected_edge:
            self.suppress_hover = True
            self.was_down = False
            self.begin_selection(point)
            return
        if self.suppress_hover:
            if not selected_down and modifiers_released():
                self.suppress_hover = False
                self.stable_since = now
            else:
                return
        down = self.settings.trigger_mode in ("both", "hover") and shortcut_down(self.settings.hotkey)
        if not self.enabled:
            self.was_down = down
            return
        if not self.ready:
            down = False  # Selection translation remains available even if OCR is unavailable.
        moved = (point-self.last_position).manhattanLength() > 6
        if moved:
            self.last_position = QPoint(point)
            self.stable_since = now
        if down and not self.was_down:
            self.attempted = None
            self.stable_since = now
        inside_popup = self.popup.isVisible() and self.popup.geometry().contains(point)
        if (down and not self.was_down and self.popup.isVisible() and
                not inside_popup and not self.popup.pin.isChecked()):
            self.dismiss()
        if (down and not inside_popup and not self.popup.pin.isChecked() and
                now-self.stable_since >= self.settings.delay_ms/1000 and
                (self.attempted is None or (point-self.attempted).manhattanLength() > 14)):
            self.attempted = QPoint(point)
            self.begin(point)
        self.was_down = down

    def begin(self, point):
        self.dismiss()
        job = self.sequence
        self.cancel = threading.Event()
        cancel = self.cancel
        settings = replace(self.settings)
        try:
            x, y, monitor = cursor_and_monitor()
        except OSError:
            return
        self.anchor_screen = QApplication.screenAt(point) or QApplication.primaryScreen()
        self.physical_monitor = monitor
        self.job_anchor = QPoint(point)
        self.active_job = True
        # Capture before showing the popup: an overlay must never appear in its own OCR input.
        self.future = self.executor.submit(self.run_job, job, cancel, settings, x, y, monitor)

    def begin_selection(self, point):
        self.dismiss()
        self.job_anchor = QPoint(point)
        self.active_job = True
        self.cancel = threading.Event()
        self.selection_settings = replace(self.settings)
        self.selection_window = foreground_window()
        if not self.selection_window or foreground_process() == os.getpid():
            self.on_result(self.sequence, "请先在网页、文档等其他应用中选中文字，再按选中翻译快捷键。", True)
            return
        self.window.state.setText("正在读取选中文字…请松开快捷键，并保持目标窗口。")
        self.selection_future = self.selection_executor.submit(
            self.lookup_selection, self.sequence, self.selection_window, self.cancel)

    def lookup_selection(self, job, window, cancel):
        try:
            status, text = read_selected_text(window, cancel)
        except Exception:
            status, text = "unavailable", ""
        if not cancel.is_set():
            self.events.selection_result.emit(job, status, text)

    @Slot(int, str, str)
    def on_selection_result(self, job, status, text):
        if job != self.sequence:
            return
        if status == "ok":
            self.translate_selection(job, text)
        elif status in ("empty", "unavailable") and self.selection_settings.copy_fallback:
            self.selection_reader.start(job, self.selection_window)
        else:
            message = {"password": "密码输入框不支持取词翻译。", "changed": "目标窗口已切换，请重新选中文字。",
                       "too_long": "选中文字超过 6000 字，请缩小选择范围。"}.get(
                           status, "未读到选中文字，请重新选择，或开启“兼容取词”。")
            self.on_result(job, message, True)

    @Slot(int, str, str)
    def on_clipboard_selection(self, job, text, error):
        if job != self.sequence:
            return
        if error:
            self.on_result(job, error, True)
        else:
            self.translate_selection(job, text)

    def translate_selection(self, job, text):
        if not text.strip() or len(text) > 6000:
            self.on_result(job, "请选择 1–6000 字的文字后重试。", True)
            return
        self.future = self.executor.submit(self.run_job, job, self.cancel,
            self.selection_settings, None, None, None, text)

    def run_job(self, job, cancel, settings, x, y, monitor, selected_text=None):
        try:
            if cancel.wait(.08):
                return
            recognized = ((selected_text, None) if selected_text is not None else
                          self.recognizer.capture(x, y, monitor, settings))
            if cancel.is_set():
                return
            if not recognized:
                self.events.result.emit(job, "这里没有识别到文字，请把鼠标移到文字上再试。", True)
                return
            source, box = recognized
            self.events.source.emit(job, source, box)
            key = (settings.base_url, settings.model, settings.target, source)
            with self.cache_lock:
                cached = self.cache.get(key)
                if cached:
                    self.cache.move_to_end(key)
            if cached:
                self.events.result.emit(job, cached, False)
                return
            last_emit = [0.0]
            def chunk(value):
                if cancel.is_set():
                    raise Cancelled()
                now = time.monotonic()
                if now-last_emit[0] >= .04:
                    self.events.chunk.emit(job, value)
                    last_emit[0] = now
            translated = stream_translation(settings, source, cancel, chunk)
            if cancel.is_set():
                return
            with self.cache_lock:
                self.cache[key] = translated
                while len(self.cache) > 100:
                    self.cache.popitem(last=False)
            self.events.result.emit(job, translated, False)
        except Cancelled:
            pass
        except UserError as exc:
            self.events.result.emit(job, str(exc), True)
        except Exception:
            logging.exception("Recognition/translation failed")
            self.events.result.emit(job, "识别失败，请稍后重试；详细信息已记录到本机日志。", True)

    @Slot(int, str, object)
    def on_source(self, job, source, box):
        if job != self.sequence:
            return
        self.popup.start(self.job_anchor)
        self.popup.source.setPlainText(source)
        self.popup.status.setText("正在翻译 → " + self.settings.target)
        self.window.state.setText("正在翻译 · " + self.trigger_description())
        if box is None:
            self.outline.hide()
            return
        screen = self.anchor_screen
        geometry = screen.geometry()
        physical = self.physical_monitor
        # Match physical desktop positions to this monitor's logical coordinate system.
        scale_x = geometry.width() / physical.width
        scale_y = geometry.height() / physical.height
        self.outline.setGeometry(round(geometry.x()+(box.x-physical.x)*scale_x)-3,
                                 round(geometry.y()+(box.y-physical.y)*scale_y)-3,
                                 round(box.width*scale_x)+6, round(box.height*scale_y)+6)
        self.source_region = QRect(self.outline.geometry())
        self.outline.show()

    @Slot(int, str)
    def on_chunk(self, job, text):
        if job == self.sequence:
            self.popup.translation.setPlainText(text)

    @Slot(int, str, bool)
    def on_result(self, job, text, error):
        if job != self.sequence:
            return
        if not self.popup.isVisible():
            self.popup.start(self.job_anchor)
        if error:
            self.window.state.setText(text)
            self.popup.status.setText("需要处理")
            self.popup.translation.setPlainText(text)
            self.popup.copy.setEnabled(False)
        else:
            self.window.state.setText("翻译完成 · " + self.trigger_description())
            self.popup.translation.setPlainText(text)
            self.popup.status.setText("已译为 " + self.settings.target + " · " + self.settings.model)
            self.popup.copy.setEnabled(True)

    def test_api(self):
        if self.testing:
            return
        from .core import validate_settings
        settings = self.window.read()
        try:
            validate_settings(settings)
        except UserError as exc:
            self.window.state.setText(str(exc))
            return
        self.testing = True
        self.test_cancel = threading.Event()
        self.window.test.setEnabled(False)
        self.window.state.setText("正在测试 API：发送示例文字 Hello, world! …")
        self.test_executor.submit(self.run_test, settings, self.test_cancel)

    def run_test(self, settings, cancel):
        try:
            value = stream_translation(settings, "Hello, world!", cancel, lambda _: None)
            message = "API 连接成功 · " + value[:100]
        except (UserError, Cancelled) as exc:
            message = str(exc)
        except Exception:
            message = "API 测试失败，请检查服务配置。"
        self.events.test_result.emit(message)

    @Slot(str)
    def on_test_result(self, message):
        self.testing = False
        self.window.test.setEnabled(True)
        self.window.state.setText(message)

    def preview(self):
        self.dismiss()
        self.popup.start(QCursor.pos())
        self.popup.pin.setChecked(True)
        self.popup.source.setPlainText("Stay curious. There is always something new to discover.")
        self.popup.translation.setPlainText("保持好奇，总有新的事物等待你去发现。")
        self.popup.status.setText("界面预览 · 示例译文 · 未调用 API")
        self.popup.copy.setEnabled(True)

    def quit(self):
        self.tick.stop()
        self.cancel.set()
        self.selection_reader.cancel()
        self.test_cancel.set()
        self.executor.shutdown(wait=False, cancel_futures=True)
        self.test_executor.shutdown(wait=False, cancel_futures=True)
        self.selection_executor.shutdown(wait=False, cancel_futures=True)
        self.tray.hide()
        self.app.quit()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("HoverTranslate")
    app.setOrganizationName("HoverTranslate")
    app.setWindowIcon(icon())
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setQuitOnLastWindowClosed(False)
    directory = settings_path().parent
    directory.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=str(directory/"app.log"), level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
    # Avoid two instances both reacting to the same global shortcut.
    lock = QLockFile(str(directory/"instance.lock"))
    lock.setStaleLockTime(30000)
    if not lock.tryLock(100):
        QMessageBox.information(None, "HoverTranslate", "程序已在运行，请双击托盘中的“译”图标打开设置。")
        return 0
    controller = Controller(app)
    if "--tray" not in sys.argv or not controller.tray.isVisible():
        controller.window.show()
    if "--preview" in sys.argv:
        QTimer.singleShot(700, controller.preview)
    app.aboutToQuit.connect(lock.unlock)
    return app.exec()
