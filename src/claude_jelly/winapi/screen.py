"""屏幕工作区、DPI 与窗口焦点相关的 Win32 辅助函数。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import traceback

from ..config import log
from .bindings import SPI_GETWORKAREA, kernel32, user32


def enable_dpi_awareness() -> None:
    try:
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except Exception:
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def work_area() -> wt.RECT:
    r = wt.RECT()
    user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0)
    if r.right <= r.left or r.bottom <= r.top:
        r = wt.RECT(0, 0, 1920, 1080)
    return r


def clamp_head(
    x: int, y: int, head: tuple[float, float, float, float]
) -> tuple[int, int]:
    """让水母脑袋完整留在工作区内（窗口本身可以伸出屏幕）。

    head 是脑袋在窗口坐标里的矩形；窗口左右留了气泡空间，
    所以不能再用窗口尺寸来夹取位置。
    """
    hx0, hy0, hx1, hy1 = head
    r = work_area()
    x = max(r.left - hx0, min(int(x), r.right - hx1))
    y = max(r.top - hy0, min(int(y), r.bottom - hy1))
    return int(round(x)), int(round(y))


def force_foreground(hwnd: int) -> None:
    try:
        if user32.GetForegroundWindow() == hwnd:
            return
        cur = kernel32.GetCurrentThreadId()
        fg = user32.GetForegroundWindow()
        fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
        attached = False
        if fg_tid and fg_tid != cur:
            attached = bool(user32.AttachThreadInput(cur, fg_tid, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        if attached:
            user32.AttachThreadInput(cur, fg_tid, False)
        if user32.GetForegroundWindow() != hwnd:
            try:
                user32.SwitchToThisWindow(hwnd, True)
            except Exception:
                pass
    except Exception:
        log("force_foreground failed\n" + traceback.format_exc())
