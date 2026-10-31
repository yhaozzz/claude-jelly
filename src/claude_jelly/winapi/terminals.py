"""Windows Terminal 窗口的识别与枚举。"""
from __future__ import annotations

import ctypes

from .bindings import WNDENUMPROC, user32

TERMINAL_WINDOW_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"


def is_terminal_window(hwnd: int) -> bool:
    """句柄是否仍然是一个 Windows Terminal 窗口。

    持久化的旧句柄可能在重启后被别的窗口复用，所以不能只信 IsWindow。
    """
    try:
        if not hwnd or not user32.IsWindow(hwnd):
            return False
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        return cls.value == TERMINAL_WINDOW_CLASS
    except Exception:
        return False


def list_terminal_windows() -> list[tuple[int, str]]:
    """枚举 Windows Terminal 的顶层窗口。"""
    out: list[tuple[int, str]] = []

    def _cb(hwnd, _lparam):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == TERMINAL_WINDOW_CLASS:
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, 512)
            out.append((int(hwnd), title.value))
        return True

    cb = WNDENUMPROC(_cb)
    user32.EnumWindows(cb, 0)
    return out
