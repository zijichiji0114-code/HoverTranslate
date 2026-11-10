import threading

from PySide6.QtCore import QPoint, QRect
import pytest

from hovertranslate import app as module
from hovertranslate.core import Settings
from test_app import until


@pytest.fixture
def controller(monkeypatch, qt_application):
    monkeypatch.setattr(module, "load_settings", lambda: Settings())
    monkeypatch.setattr(module, "Recognizer", lambda: object())
    instance = module.Controller(qt_application)
    instance.tick.stop()
    until(qt_application, lambda: instance.ready)
    instance.job_anchor = QPoint(100, 100)
    instance.active_job = True
    instance.source_region = QRect(80, 90, 120, 25)
    instance.cancel = threading.Event()
    instance.popup.start(instance.job_anchor)
    yield instance
    instance.quit()
    instance.executor.shutdown(wait=True)
    instance.selection_executor.shutdown(wait=True)
    instance.test_executor.shutdown(wait=True)


def test_leaving_source_hides_promptly_even_close_to_original_cursor(controller):
    point = QPoint(65, 100)  # Only 35px from the anchor: the old 150px radius kept it open.
    controller.update_visibility(point, 10)
    assert controller.popup.isVisible()
    old_job = controller.sequence
    controller.update_visibility(point, 10.19)
    assert not controller.popup.isVisible()
    assert controller.cancel.is_set()
    controller.on_result(old_job, "late response", False)
    assert not controller.popup.isVisible()


def test_entering_popup_during_transition_keeps_it_open(controller):
    controller.update_visibility(QPoint(65, 100), 10)
    controller.update_visibility(controller.popup.geometry().center(), 10.1)
    controller.update_visibility(controller.popup.geometry().center(), 12)
    assert controller.popup.isVisible()
    assert controller.hide_since is None


def test_leaving_popup_hides_it(controller):
    controller.update_visibility(controller.popup.geometry().center(), 10)
    controller.update_visibility(QPoint(740, 740), 11)
    controller.update_visibility(QPoint(740, 740), 11.19)
    assert not controller.popup.isVisible()


def test_pin_preserves_explicitly_fixed_popup(controller):
    controller.popup.pin.setChecked(True)
    controller.update_visibility(QPoint(740, 740), 10)
    controller.update_visibility(QPoint(740, 740), 20)
    assert controller.popup.isVisible()


def test_moving_away_cancels_before_a_slow_result_appears(controller):
    controller.popup.hide()
    old_job = controller.sequence
    controller.update_visibility(QPoint(740, 740), 10)
    controller.update_visibility(QPoint(740, 740), 10.19)
    controller.on_result(old_job, "late response", False)
    assert controller.cancel.is_set()
    assert not controller.popup.isVisible()


@pytest.mark.parametrize("suppress", [False, True])
def test_poll_auto_hides_while_shortcut_is_still_held(controller, monkeypatch, suppress):
    controller.suppress_hover = suppress
    controller.was_down = True
    controller.was_selected_down = True
    controller.stable_since = 1000
    controller.hide_since = 1
    monkeypatch.setattr(module.time, "monotonic", lambda: 10)
    monkeypatch.setattr(module.QCursor, "pos", lambda: QPoint(65, 100))
    monkeypatch.setattr(module, "pressed", lambda _: False)
    monkeypatch.setattr(module, "shortcut_down", lambda _: True)
    monkeypatch.setattr(module, "selection_shortcut_down", lambda _: suppress)
    monkeypatch.setattr(module, "modifiers_released", lambda: False)
    controller.poll()
    assert not controller.popup.isVisible()
