"""Exercise the controller, live HTTP SSE, and Qt popup together with known fixture text."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PySide6.QtCore import QPoint
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QApplication

from hovertranslate import app as module
from hovertranslate.core import Rect, Settings


def until(app, predicate, timeout=5):
    end = time.monotonic()+timeout
    while time.monotonic() < end:
        app.processEvents()
        if predicate():
            return
        threading.Event().wait(.015)  # Release Python's GIL for HTTP and OCR worker threads.
    raise AssertionError("Timed out waiting for desktop app result")


def test_shortcut_to_http_to_popup_and_stale_result(monkeypatch):
    received = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for chunk in ["保持", "好奇。"]:
                event = {"choices": [{"delta": {"content": chunk}}]}
                self.wfile.write(("data: "+json.dumps(event, ensure_ascii=False)+"\n\n").encode())
                self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")

    class FixtureRecognizer:
        def capture(self, x, y, monitor, settings):
            return "Stay curious.", Rect(x-40, y-10, 120, 24)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(module, "Recognizer", FixtureRecognizer)
    monkeypatch.setattr(module, "load_settings", lambda: Settings(
        base_url=f"http://127.0.0.1:{server.server_port}/v1", model="fixture", delay_ms=250))
    monkeypatch.setattr(module, "cursor_and_monitor", lambda: (100, 100, Rect(0, 0, 800, 800)))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    application = QApplication.instance() or QApplication([])
    controller = module.Controller(application)
    controller.tick.stop()
    try:
        until(application, lambda: controller.ready)
        monkeypatch.setattr(module, "shortcut_down", lambda _: True)
        monkeypatch.setattr(module, "pressed", lambda _: False)
        controller.poll()  # first modifier press begins a fresh dwell
        controller.stable_since = time.monotonic()-1
        controller.poll()  # stable hover submits recognition and translation
        try:
            until(application, lambda: controller.popup.copy.isEnabled())
        except AssertionError as exc:
            raise AssertionError((controller.sequence, controller.popup.isVisible(),
                controller.popup.status.text(), controller.popup.translation.toPlainText(),
                received, controller.future.done())) from exc
        assert controller.popup.source.toPlainText() == "Stay curious."
        assert controller.popup.translation.toPlainText() == "保持好奇。"
        assert received[0]["messages"][1]["content"] == "Stay curious."
        screen = QApplication.screenAt(controller.popup.anchor) or QApplication.primaryScreen()
        assert screen.availableGeometry().contains(controller.popup.geometry())
        old_job = controller.sequence
        controller.popup.pin.setChecked(True)
        controller.dismiss()
        assert not controller.popup.pin.isChecked()
        controller.on_result(old_job, "stale response", False)
        assert not controller.popup.isVisible()
        controller.window.show()
        application.processEvents()
        button_point = controller.window.save.mapTo(controller.window, QPoint(0, 0))
        assert controller.window.rect().contains(button_point)
        assert controller.window.save.isVisible()
    finally:
        controller.quit()
        controller.window.hide()
        controller.executor.shutdown(wait=True)
        controller.test_executor.shutdown(wait=True)
        server.shutdown()
        server.server_close()
