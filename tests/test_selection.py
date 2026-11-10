from dataclasses import replace
import threading
import time

from PySide6.QtCore import QMimeData
from PySide6.QtWidgets import QApplication
import pytest

from hovertranslate import app as app_module
from hovertranslate import clipboard_selection as clip_module
from hovertranslate.core import Settings, UserError, load_settings, validate_settings
from hovertranslate.selection import _uia_module, read_selected_text
from test_app import until


def test_old_settings_enable_both_modes_by_default(tmp_path):
    path = tmp_path/"settings.json"
    path.write_text('{"base_url":"https://api.deepseek.com","model":"deepseek-chat"}', encoding="utf8")
    settings = load_settings(path)
    assert settings.trigger_mode == "both"
    assert settings.selection_hotkey == "Ctrl + Shift + F8"


@pytest.mark.parametrize("field,value", [("trigger_mode", "invalid"), ("selection_hotkey", "invalid"),
                                         ("copy_fallback", "yes")])
def test_selection_settings_validation(field, value):
    with pytest.raises(UserError):
        validate_settings(replace(Settings(), **{field: value}))


def test_selected_shortcut_reads_once_and_does_not_use_ocr(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    class Recognizer:
        def capture(self, *args):
            raise AssertionError("Selected-text translation must not use OCR")
    reads = []
    def reader(window, cancel):
        reads.append(window)
        return "ok", "Exactly selected\ntext, with spaces."
    def translate(settings, text, cancel, chunk):
        assert text == "Exactly selected\ntext, with spaces."
        chunk("选中译文")
        return "选中译文"
    monkeypatch.setattr(app_module, "load_settings", lambda: Settings(trigger_mode="selected"))
    monkeypatch.setattr(app_module, "Recognizer", Recognizer)
    monkeypatch.setattr(app_module, "read_selected_text", reader)
    monkeypatch.setattr(app_module, "stream_translation", translate)
    monkeypatch.setattr(app_module, "foreground_window", lambda: 12345)
    monkeypatch.setattr(app_module, "foreground_process", lambda: 0)
    monkeypatch.setattr(app_module, "pressed", lambda _: False)
    monkeypatch.setattr(app_module, "selection_shortcut_down", lambda _: True)
    controller = app_module.Controller(application)
    controller.tick.stop()
    try:
        until(application, lambda: controller.ready)
        controller.ready = False  # OCR failure must not disable direct selection translation.
        controller.poll()
        controller.poll()  # A held hotkey must not repeat the request.
        until(application, lambda: controller.popup.copy.isEnabled())
        assert reads == [12345]
        assert controller.popup.source.toPlainText() == "Exactly selected\ntext, with spaces."
        assert controller.popup.translation.toPlainText() == "选中译文"
        assert not controller.outline.isVisible()
        assert controller.window.trigger.currentIndex() == 2
        assert not controller.window.hotkey.isEnabled()
        assert controller.window.selected_hotkey.isEnabled()
    finally:
        controller.quit()
        controller.executor.shutdown(wait=True)
        controller.selection_executor.shutdown(wait=True)
        controller.test_executor.shutdown(wait=True)


def clipboard_fixture(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    app = QApplication.instance() or QApplication([])
    clipboard = app.clipboard()
    original = QMimeData()
    original.setText("old clipboard, never translate this")
    original.setHtml("<b>old clipboard</b>")
    clipboard.setMimeData(original)
    sequence = [10]
    released = [True]
    foreground = [123]
    monkeypatch.setattr(clip_module, "clipboard_sequence", lambda: sequence[0])
    monkeypatch.setattr(clip_module, "foreground_window", lambda: foreground[0])
    monkeypatch.setattr(clip_module, "modifiers_released", lambda: released[0])
    return app, clipboard, sequence, released, foreground


def test_copy_fallback_waits_for_release_and_restores_text_html(monkeypatch):
    app, clipboard, sequence, released, _ = clipboard_fixture(monkeypatch)
    sent = []
    def copy():
        sent.append(True)
        clipboard.setText("actual selected text")
        sequence[0] += 1
    monkeypatch.setattr(clip_module, "send_copy", copy)
    reader = clip_module.ClipboardSelection()
    results = []
    reader.finished.connect(lambda *values: results.append(values))
    released[0] = False
    reader.start(9, 123)
    assert sent == []
    released[0] = True
    reader.poll()
    reader.poll()
    assert sent == [True]
    assert results == [(9, "actual selected text", "")]
    assert clipboard.text() == "old clipboard, never translate this"
    assert clipboard.mimeData().html() == "<b>old clipboard</b>"


def test_no_clipboard_change_never_translates_previous_clipboard(monkeypatch):
    app, clipboard, sequence, _, _ = clipboard_fixture(monkeypatch)
    monkeypatch.setattr(clip_module, "send_copy", lambda: None)
    reader = clip_module.ClipboardSelection()
    results = []
    reader.finished.connect(lambda *values: results.append(values))
    reader.start(3, 123)
    reader.poll()
    assert results == []
    reader.deadline = time.monotonic()-1
    reader.poll()
    assert results[0][1] == "" and results[0][2]
    assert clipboard.text() == "old clipboard, never translate this"


def test_focus_change_aborts_before_copy(monkeypatch):
    app, clipboard, sequence, released, foreground = clipboard_fixture(monkeypatch)
    sent = []
    monkeypatch.setattr(clip_module, "send_copy", lambda: sent.append(True))
    released[0] = False
    reader = clip_module.ClipboardSelection()
    results = []
    reader.finished.connect(lambda *values: results.append(values))
    reader.start(4, 123)
    foreground[0] = 999
    released[0] = True
    reader.poll()
    assert sent == []
    assert results[0][1] == "" and "窗口" in results[0][2]


def test_restore_does_not_overwrite_newer_clipboard(monkeypatch):
    app, clipboard, sequence, _, _ = clipboard_fixture(monkeypatch)
    reader = clip_module.ClipboardSelection()
    reader.snapshot = QMimeData()
    reader.snapshot.setText("saved old clipboard")
    reader.copied_sequence = 11
    clipboard.setText("new user clipboard")
    sequence[0] = 12
    reader.cancel()
    assert clipboard.text() == "new user clipboard"


def test_uia_helper_exits_for_invalid_target_without_reading_selection():
    status, text = read_selected_text(-1, threading.Event(), timeout=4)
    assert status == "changed"
    assert text == ""


def test_fresh_source_checkout_generates_uia_wrappers(monkeypatch):
    import builtins
    import comtypes.client
    original_import = builtins.__import__
    generated = object()
    calls = []
    def import_without_wrapper(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "comtypes.gen" and "UIAutomationClient" in fromlist:
            raise ImportError("No generated wrapper in a fresh installation")
        return original_import(name, globals, locals, fromlist, level)
    def generate(name):
        calls.append(name)
        return generated
    monkeypatch.setattr(builtins, "__import__", import_without_wrapper)
    monkeypatch.setattr(comtypes.client, "GetModule", generate)
    assert _uia_module() is generated
    assert calls == ["UIAutomationCore.dll"]
