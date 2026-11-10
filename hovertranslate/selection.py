"""Read UI Automation selections in an isolated process so a slow provider cannot hang the app."""
import multiprocessing
import sys
import time


MAX_SELECTION = 6000


def _uia_module():
    try:
        from comtypes.gen import UIAutomationClient
        return UIAutomationClient
    except ImportError:
        # A fresh source checkout has no generated wrappers yet. Frozen builds include them.
        from comtypes.client import GetModule
        return GetModule("UIAutomationCore.dll")


def _uia_worker(connection, expected_window):
    try:
        sys.coinit_flags = 0  # UI Automation client runs in a dedicated MTA process.
        from comtypes.client import CreateObject
        UIA = _uia_module()
        from .windows import foreground_window
        if foreground_window() != expected_window:
            connection.send(("changed", ""))
            return
        automation = CreateObject(UIA.CUIAutomation, interface=UIA.IUIAutomation)
        element = automation.GetFocusedElement()
        walker = automation.ControlViewWalker
        for _ in range(6):
            if not element:
                break
            try:
                if element.CurrentIsPassword:
                    connection.send(("password", ""))
                    return
                pattern = element.GetCurrentPattern(UIA.UIA_TextPatternId)
                if pattern:
                    ranges = pattern.QueryInterface(UIA.IUIAutomationTextPattern).GetSelection()
                    values = [ranges.GetElement(i).GetText(MAX_SELECTION+1)
                              for i in range(min(ranges.Length, 32))]
                    text = "\n".join(value for value in values if value).strip()
                    if foreground_window() != expected_window:
                        connection.send(("changed", ""))
                        return
                    if text:
                        connection.send(("too_long", "") if len(text) > MAX_SELECTION else ("ok", text))
                        return
            except Exception:
                pass  # A child control can delegate its text pattern to its parent.
            element = walker.GetParentElement(element)
        connection.send(("empty", ""))
    except Exception:
        connection.send(("unavailable", ""))
    finally:
        connection.close()


def read_selected_text(expected_window, cancel, timeout=2.0):
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=_uia_worker, args=(child, expected_window), daemon=True)
    try:
        process.start()
        child.close()
        deadline = time.monotonic()+timeout
        while not cancel.is_set() and time.monotonic() < deadline:
            if parent.poll(.04):
                return parent.recv()
        return ("cancelled", "") if cancel.is_set() else ("unavailable", "")
    except (EOFError, OSError):
        return "unavailable", ""
    finally:
        parent.close()
        child.close()
        if process.pid:
            if process.is_alive():
                process.terminate()
            process.join(timeout=.3)
