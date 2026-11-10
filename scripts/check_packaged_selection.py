"""Verify the frozen UIA helper's imports and process exit without reading any selection."""
import multiprocessing
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hovertranslate.selection import read_selected_text


if __name__ == "__main__":
    executable = Path(sys.argv[1]).resolve()
    if not executable.is_file():
        raise SystemExit("Executable does not exist")
    sys.executable = str(executable)
    sys._base_executable = str(executable)  # Prevent venv launch redirection during this check.
    sys.frozen = True
    multiprocessing.set_executable(str(executable))
    status, text = read_selected_text(-1, threading.Event(), timeout=8)
    assert (status, text) == ("changed", ""), (status, text)
    print("Packaged selection helper: PASS (imports loaded; invalid target rejected)")
