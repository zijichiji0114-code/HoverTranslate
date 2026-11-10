import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="session", autouse=True)
def qt_application():
    # Keep one Python owner alive until clipboard MIME objects have been released.
    app = QApplication.instance() or QApplication([])
    yield app
    app.clipboard().clear()
    app.processEvents()
