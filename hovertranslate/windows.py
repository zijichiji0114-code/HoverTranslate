"""Physical desktop coordinates are used only for screenshots, never Qt window placement."""
import ctypes
from ctypes import wintypes

from .core import Rect

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
user32.MonitorFromPoint.restype = wintypes.HANDLE


class MonitorInfo(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("monitor", wintypes.RECT),
                ("work", wintypes.RECT), ("flags", wintypes.DWORD)]


user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
user32.GetMonitorInfoW.restype = wintypes.BOOL


def pressed(key):
    return bool(user32.GetAsyncKeyState(key) & 0x8000)


def shortcut_down(combo):
    keys = {"Ctrl + Alt": (0x11, 0x12), "Ctrl + Shift": (0x11, 0x10),
            "Alt + Shift": (0x12, 0x10)}[combo]
    return all(pressed(key) for key in keys) and not pressed(0x01) and not pressed(0x02)


def selection_shortcut_down(combo):
    keys = {"Ctrl + Shift + F8": (0x11, 0x10, 0x77), "Ctrl + Alt + T": (0x11, 0x12, 0x54),
            "Alt + F8": (0x12, 0x77)}[combo]
    return all(pressed(key) for key in keys) and not pressed(0x01) and not pressed(0x02)


def foreground_window():
    return user32.GetForegroundWindow()


def foreground_process():
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(foreground_window(), ctypes.byref(pid))
    return pid.value


def clipboard_sequence():
    return user32.GetClipboardSequenceNumber()


def modifiers_released():
    return not any(pressed(key) for key in (0x10, 0x11, 0x12, 0x77, 0x54))


def send_copy():
    """Copy only after the caller has verified key release and the original foreground HWND."""
    class MouseInput(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]
    class KeyInput(ctypes.Structure):
        _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]
    class HardwareInput(ctypes.Structure):
        _fields_ = [("message", wintypes.DWORD), ("low", wintypes.WORD), ("high", wintypes.WORD)]
    class InputData(ctypes.Union):
        _fields_ = [("mouse", MouseInput), ("key", KeyInput), ("hardware", HardwareInput)]
    class Input(ctypes.Structure):
        _anonymous_ = ("data",)
        _fields_ = [("type", wintypes.DWORD), ("data", InputData)]
    entries = (Input * 4)()
    for entry, (key, flags) in zip(entries, [(0x11, 0), (0x43, 0), (0x43, 2), (0x11, 2)]):
        entry.type = 1
        entry.key = KeyInput(key, 0, flags, 0, 0)
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
    user32.SendInput.restype = wintypes.UINT
    if user32.SendInput(4, entries, ctypes.sizeof(Input)) != 4:
        raise OSError("无法向目标应用发送复制操作；管理员窗口可能需要相同权限。")


def cursor_and_monitor():
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        raise OSError("无法获取鼠标位置")
    monitor = user32.MonitorFromPoint(point, 2)
    info = MonitorInfo()
    info.size = ctypes.sizeof(info)
    if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        raise OSError("无法获取屏幕信息")
    r = info.monitor
    return point.x, point.y, Rect(r.left, r.top, r.right-r.left, r.bottom-r.top)
