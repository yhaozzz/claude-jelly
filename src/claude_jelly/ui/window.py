"""无边框分层窗口：创建、DIB 合成、移动与透明度命中查询。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

import numpy as np
from PIL import Image

from ..config import WINDOW_CLASS, WINDOW_TITLE, log
from ..winapi.bindings import (
    AC_SRC_ALPHA,
    AC_SRC_OVER,
    BITMAPINFO,
    BITMAPINFOHEADER,
    BLENDFUNCTION,
    HWND_NOTOPMOST,
    HWND_TOPMOST,
    SIZE,
    SW_SHOWNA,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_NOZORDER,
    ULW_ALPHA,
    WNDCLASSEXW,
    WNDPROC,
    WS_EX_LAYERED,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    WS_POPUP,
    gdi32,
    kernel32,
    user32,
)
from ..winapi.screen import work_area
from .render import premultiplied_bgra


class LayeredWindow:
    """承载水母的透明置顶窗口。窗口本身不持有业务状态。"""

    def __init__(
        self,
        wndproc,
        pos: tuple[int, int],
        width: int,
        height: int,
        topmost: bool,
        title: str = WINDOW_TITLE,
    ) -> None:
        # 必须持有 WNDPROC 引用，否则回调会被回收
        self._wndproc_ref = WNDPROC(wndproc)
        self.hwnd = 0
        self.memdc = 0
        self.dib = 0
        self.dib_bits = ctypes.c_void_p()
        self.dib_w = 0
        self.dib_h = 0
        self.alpha: np.ndarray | None = None

        self._register_class()
        self._create(pos, width, height, topmost, title)

    # ---------------- 窗口生命周期 ----------------
    def _register_class(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, 32512)  # IDC_ARROW
        wc.lpszClassName = WINDOW_CLASS
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                log(f"RegisterClassExW failed: {err}")

    def _create(
        self,
        pos: tuple[int, int],
        width: int,
        height: int,
        topmost: bool,
        title: str,
    ) -> None:
        ex = WS_EX_LAYERED | WS_EX_TOOLWINDOW
        if topmost:
            ex |= WS_EX_TOPMOST
        hinst = kernel32.GetModuleHandleW(None)
        self.hwnd = user32.CreateWindowExW(
            ex, WINDOW_CLASS, title, WS_POPUP,
            pos[0], pos[1], width, height,
            None, None, hinst, None,
        )
        if not self.hwnd:
            raise OSError(f"CreateWindowExW failed: {ctypes.get_last_error()}")
        self._ensure_dib(width, height)

    def show(self) -> None:
        user32.ShowWindow(self.hwnd, SW_SHOWNA)

    def destroy(self) -> None:
        if self.hwnd:
            user32.DestroyWindow(self.hwnd)
            self.hwnd = 0

    # ---------------- 绘制 ----------------
    def _ensure_dib(self, w: int, h: int) -> None:
        if self.memdc and self.dib_w == w and self.dib_h == h:
            return
        if self.dib:
            gdi32.DeleteObject(self.dib)
            self.dib = 0
        if self.memdc:
            gdi32.DeleteDC(self.memdc)
            self.memdc = 0

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = w
        bmi.bmiHeader.biHeight = -h  # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        bmi.bmiHeader.biCompression = 0
        bits = ctypes.c_void_p()
        self.memdc = gdi32.CreateCompatibleDC(None)
        self.dib = gdi32.CreateDIBSection(
            self.memdc, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0
        )
        if not self.dib:
            raise OSError(f"CreateDIBSection failed: {ctypes.get_last_error()}")
        gdi32.SelectObject(self.memdc, self.dib)
        self.dib_bits = bits
        self.dib_w, self.dib_h = w, h

    def paint(self, img: Image.Image, const_alpha: float) -> None:
        self._ensure_dib(img.width, img.height)
        data = premultiplied_bgra(img)
        ctypes.memmove(self.dib_bits, data, len(data))
        size = SIZE(img.width, img.height)
        src = wt.POINT(0, 0)
        alpha = max(0, min(255, int(round(const_alpha))))
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, alpha, AC_SRC_ALPHA)
        ok = user32.UpdateLayeredWindow(
            self.hwnd, None, None, ctypes.byref(size), self.memdc,
            ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA,
        )
        if not ok:
            log(f"UpdateLayeredWindow failed: {ctypes.get_last_error()}")
        self.alpha = np.asarray(img.getchannel("A"))

    def alpha_at(self, x: int, y: int) -> int:
        if self.alpha is None:
            return 0
        h, w = self.alpha.shape
        if 0 <= x < w and 0 <= y < h:
            return int(self.alpha[y, x])
        return 0

    # ---------------- 位置 / 置顶 ----------------
    def move(self, x: int, y: int, topmost: bool) -> None:
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST if topmost else ctypes.c_void_p(0),
            int(x), int(y), 0, 0, SWP_NOSIZE | SWP_NOACTIVATE,
        )

    def set_bounds(self, x: int, y: int, w: int, h: int) -> None:
        user32.SetWindowPos(
            self.hwnd, None, x, y, w, h, SWP_NOZORDER | SWP_NOACTIVATE,
        )

    def set_topmost(self, topmost: bool) -> None:
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST if topmost else HWND_NOTOPMOST,
            0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )


def clip_to_work_area(img: Image.Image, pos: tuple[int, int]) -> Image.Image:
    """把窗口伸出工作区（任务栏区域）的部分裁成透明。"""
    r = work_area()
    x0 = r.left - pos[0]
    y0 = r.top - pos[1]
    x1 = r.right - pos[0]
    y1 = r.bottom - pos[1]
    w, h = img.size
    cx0, cy0 = max(0, min(w, x0)), max(0, min(h, y0))
    cx1, cy1 = max(0, min(w, x1)), max(0, min(h, y1))
    if cx0 == 0 and cy0 == 0 and cx1 == w and cy1 == h:
        return img
    arr = np.array(img)
    mask = np.zeros((h, w), dtype=bool)
    mask[cy0:cy1, cx0:cx1] = True
    arr[~mask] = 0
    return Image.fromarray(arr, "RGBA")
