"""悬浮水母窗口：窗口过程、交互菜单与启动逻辑。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path

import numpy as np
from PIL import Image

from .core import (
    APP_NAME,
    CLAUDE,
    CONFIG_PATH,
    LOCAL_DIR,
    TERM_TITLE,
    WINDOW_CLASS,
    WINDOW_TITLE,
    WT,
    clamp_head,
    enable_dpi_awareness,
    force_foreground,
    is_terminal_window,
    list_terminal_windows,
    load_config,
    log,
    save_config,
    set_autostart,
    shortcut_exists,
    work_area,
)
from .providers import (
    PROVIDER_DEFAULTS,
    PROVIDER_LABELS,
    PROVIDER_ORDER,
    bat_value,
    provider_values,
    read_claude_env,
    write_launch_script,
)
from .render import (
    BASE_H,
    BASE_W,
    BUBBLE_EXIT_OFFSET,
    BUBBLE_PAD,
    BUBBLE_RISE,
    EDGE_PEEK,
    EDGE_PEEK_SIDE,
    EDGE_PEEK_TOP,
    EDGE_SNAP_RADIUS,
    REDOCK_DELAY,
    SPRITE_CY,
    body_rect,
    clear_sprite_cache,
    draw_frame,
    head_rect,
    premultiplied_bgra,
)
from .win32 import (
    AC_SRC_ALPHA,
    AC_SRC_OVER,
    BITMAPINFO,
    BITMAPINFOHEADER,
    BLENDFUNCTION,
    ERROR_ALREADY_EXISTS,
    HOTKEY_ID,
    HTCLIENT,
    HTTRANSPARENT,
    HWND_NOTOPMOST,
    HWND_TOPMOST,
    MF_CHECKED,
    MF_GRAYED,
    MF_POPUP,
    MF_SEPARATOR,
    MF_STRING,
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    SIZE,
    SW_HIDE,
    SW_RESTORE,
    SW_SHOW,
    SW_SHOWNA,
    SWP_NOACTIVATE,
    SWP_NOMOVE,
    SWP_NOSIZE,
    SWP_NOZORDER,
    TPM_NONOTIFY,
    TPM_RETURNCMD,
    TPM_RIGHTBUTTON,
    ULW_ALPHA,
    WM_APP_LAUNCHED,
    WM_CLOSE,
    WM_DESTROY,
    WM_ERASEBKGND,
    WM_HOTKEY,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MOUSEMOVE,
    WM_NCHITTEST,
    WM_NULL,
    WM_RBUTTONUP,
    WM_TIMER,
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

SIZE_PRESETS = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2)
OPACITY_PRESETS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)
FLOAT_PRESETS = (0.0, 0.5, 1.0, 2.0)
FLOAT_LABELS = ("静止", "慢", "正常", "快")


class JellyApp:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.dpi_scale = max(1.0, user32.GetDpiForSystem() / 96.0)
        self.size_factor = min(1.6, max(0.4, float(self.cfg.get("size", 0.7))))
        self.idle_opacity = min(1.0, max(0.1, float(self.cfg.get("opacity", 0.4))))
        self.float_speed = min(3.0, max(0.0, float(self.cfg.get("float_speed", 1.0))))
        self.anim_offset = 0.0   # 切换速度时用来保持相位连续

        # ---- 大模型接口（默认使用 claude 官方登录） ----
        saved_provider = self.cfg.get("provider")
        self.provider = (
            saved_provider if saved_provider in PROVIDER_ORDER else "default"
        )
        raw_providers = self.cfg.get("providers")
        self.provider_cfg: dict[str, dict] = {}
        if isinstance(raw_providers, dict):
            for name, conf in raw_providers.items():
                if name in PROVIDER_ORDER and isinstance(conf, dict):
                    self.provider_cfg[name] = dict(conf)
        if "provider" not in self.cfg:
            # 首次使用：跟随 Claude Code 现有 settings.json 的接口，避免行为突变
            env = read_claude_env()
            url = env.get("ANTHROPIC_BASE_URL", "")
            model = env.get("ANTHROPIC_MODEL", "")
            token = env.get("ANTHROPIC_AUTH_TOKEN", "")
            if "deepseek" in url.lower():
                self.provider = "deepseek"
                self.provider_cfg["deepseek"] = {
                    "base_url": url,
                    "model": model or PROVIDER_DEFAULTS["deepseek"]["model"],
                    "api_key": token,
                }
            elif url:
                self.provider = "custom"
                self.provider_cfg["custom"] = {
                    "base_url": url,
                    "model": model,
                    "api_key": token,
                }
        self.show_tip = bool(self.cfg.get("show_tip", False))
        self.scale = self.dpi_scale * self.size_factor
        self.pw = max(1, int(round(BASE_W * self.scale)))
        self.ph = max(1, int(round(BASE_H * self.scale)))

        r = work_area()
        head = head_rect(self.scale)
        hx0, hy0, hx1, hy1 = head
        default_x = int(round(r.right - 16 - hx1))
        default_y = int(round(r.bottom - 16 - hy1))
        x = int(self.cfg.get("x", default_x))
        y = int(self.cfg.get("y", default_y))
        if int(self.cfg.get("layout", 1)) < 2:
            # 旧版窗口没有气泡留白：左移一个留白宽度，保持水母视觉位置不变
            x -= int(round(BUBBLE_PAD * self.scale))
            self.cfg["layout"] = 2
            save_config(self.cfg)
        x, y = clamp_head(x, y, head)
        self.pos = [x, y]
        self.topmost = bool(self.cfg.get("topmost", True))

        # ---- 边缘躲藏状态（靠近边缘才躲，拖离边缘即恢复悬浮） ----
        saved_edge = self.cfg.get("dock")
        self.dock_edge: str | None = (
            saved_edge if saved_edge in ("left", "right", "top", "bottom")
            else self._nearest_edge()
        )
        self.hidden = self.dock_edge is not None
        self.reveal = False      # 躲藏中的水母是否已探出完整身体
        self.reveal_armed = True  # 鼠标先离开一次后才允许悬停探出
        self.redock_at = 0.0
        self.anim_target: tuple[int, int] | None = None
        if self.dock_edge:
            self.pos = list(self._dock_pos(self.dock_edge, revealed=False))

        self.hwnd: int = 0
        self.memdc: int = 0
        self.dib: int = 0
        self.dib_bits = ctypes.c_void_p()
        self.dib_w = 0
        self.dib_h = 0

        self.img: Image.Image | None = None
        self.alpha: np.ndarray | None = None
        self.tip_rect: tuple[int, int, int, int] | None = None

        self.t0 = time.monotonic()
        self.hover = False
        self.vis_alpha = 255.0 * self.idle_opacity
        self.hover_since = 0.0
        self.tip_shown = False
        self.dragging = False
        self.drag_moved = False
        self.drag_cursor = (0, 0)
        self.drag_origin = (0, 0)

        # 记住水母打开过的终端窗口（新→旧），关掉当前窗口后能接管另一个
        self.term_history: list[int] = []
        raw_history = self.cfg.get("term_hwnds", [])
        if isinstance(raw_history, list):
            for item in raw_history:
                try:
                    h = int(item)
                except (TypeError, ValueError):
                    continue
                if h not in self.term_history and is_terminal_window(h):
                    self.term_history.append(h)
        self.term_hwnd: int = self.term_history[0] if self.term_history else 0
        self.launching = False
        self.error_until = 0.0
        self.toggle_msg = user32.RegisterWindowMessageW("ClaudeJelly_Toggle_v1")

        self.wndproc_ref = WNDPROC(self._wndproc)
        self._register_class()
        self._create_window()

    # ---------------- 窗口 ----------------
    def _register_class(self) -> None:
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.style = 0
        wc.lpfnWndProc = self.wndproc_ref
        wc.hInstance = hinst
        wc.hCursor = user32.LoadCursorW(None, 32512)  # IDC_ARROW
        wc.lpszClassName = WINDOW_CLASS
        if not user32.RegisterClassExW(ctypes.byref(wc)):
            err = ctypes.get_last_error()
            if err != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                log(f"RegisterClassExW failed: {err}")

    def _create_window(self) -> None:
        ex = WS_EX_LAYERED | WS_EX_TOOLWINDOW
        if self.topmost:
            ex |= WS_EX_TOPMOST
        hinst = kernel32.GetModuleHandleW(None)
        self.hwnd = user32.CreateWindowExW(
            ex, WINDOW_CLASS, WINDOW_TITLE, WS_POPUP,
            self.pos[0], self.pos[1], self.pw, self.ph,
            None, None, hinst, None,
        )
        if not self.hwnd:
            raise OSError(f"CreateWindowExW failed: {ctypes.get_last_error()}")

        self._ensure_dib(self.pw, self.ph)
        self._render()
        user32.ShowWindow(self.hwnd, SW_SHOWNA)
        user32.SetTimer(self.hwnd, 1, 40, None)

        ok = user32.RegisterHotKey(
            self.hwnd, HOTKEY_ID,
            MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("J"),
        )
        log(f"hotkey registered: {bool(ok)}")

    def run(self) -> None:
        msg = wt.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    # ---------------- 绘制/合成 ----------------
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

    def _state(self) -> str:
        if self.launching:
            return "launching"
        if time.monotonic() < self.error_until:
            return "error"
        h = self.term_hwnd
        if h and user32.IsWindow(h):
            if user32.IsWindowVisible(h) and not user32.IsIconic(h):
                return "visible"
            return "hidden"
        return "none"

    def _tip_text(self, state: str) -> str:
        if state == "visible":
            return "收起窗口"
        if state == "launching":
            return "正在启动…"
        if state == "error":
            return "启动失败"
        return "打开 Claude Code"

    def _focus_side(self) -> int:
        """气泡和状态灯朝屏幕内侧的方向：-1 向左，+1 向右。"""
        hx0, _hy0, hx1, _hy1 = self._head_rect()
        r = work_area()
        if self.dock_edge == "right":
            return -1
        if self.dock_edge == "left":
            return 1
        cx = self.pos[0] + (hx0 + hx1) / 2.0
        return -1 if cx > (r.left + r.right) / 2.0 else 1

    def _bubble_low(self) -> bool:
        """贴上边缘时泡泡改从身体下半部出，否则还没看完就飘出屏幕了。"""
        r = work_area()
        emit_y = self.pos[1] + (SPRITE_CY + BUBBLE_EXIT_OFFSET) * self.scale
        return emit_y < r.top + BUBBLE_RISE * 0.6 * self.scale

    def _render(self) -> None:
        if not self.hwnd:
            return
        t = (time.monotonic() - self.t0) * self.float_speed + self.anim_offset
        state = self._state()
        # 贴在上边缘：不吐泡泡，改成挂着晃触手（终端在显示时才晃）
        hanging = self.dock_edge == "top"
        img, tip_rect = draw_frame(
            self.scale, t, self.hover, self.tip_shown and self.show_tip,
            self._tip_text(state), state,
            self.hidden and not hanging,
            0 if hanging else self._focus_side(),
            self._bubble_low(),
            hanging and state == "visible",
        )
        img = self._clip_to_work_area(img)
        if img.size != (self.dib_w, self.dib_h):
            self._ensure_dib(img.width, img.height)
        self.img = img
        self.alpha = np.asarray(img.getchannel("A"))
        self.tip_rect = tip_rect
        self._paint(img)

    def _paint(self, img: Image.Image) -> None:
        data = premultiplied_bgra(img)
        ctypes.memmove(self.dib_bits, data, len(data))
        size = SIZE(img.width, img.height)
        src = wt.POINT(0, 0)
        const_alpha = max(0, min(255, int(round(self.vis_alpha))))
        blend = BLENDFUNCTION(AC_SRC_OVER, 0, const_alpha, AC_SRC_ALPHA)
        ok = user32.UpdateLayeredWindow(
            self.hwnd, None, None, ctypes.byref(size), self.memdc,
            ctypes.byref(src), 0, ctypes.byref(blend), ULW_ALPHA,
        )
        if not ok:
            log(f"UpdateLayeredWindow failed: {ctypes.get_last_error()}")

    def _alpha_at(self, x: int, y: int) -> int:
        if self.alpha is None:
            return 0
        h, w = self.alpha.shape
        if 0 <= x < w and 0 <= y < h:
            return int(self.alpha[y, x])
        return 0

    def _is_hit(self, x: int, y: int) -> bool:
        """鼠标是否落在水母身体上（泡泡不算，避免挡住点击/误触）。"""
        bx0, by0, bx1, by1 = body_rect(self.scale)
        if not (bx0 <= x <= bx1 and by0 <= y <= by1):
            return False
        return self._alpha_at(x, y) >= 80

    def _in_tooltip(self, x: int, y: int) -> bool:
        if not self.tip_shown or not self.tip_rect:
            return False
        x0, y0, x1, y1 = self.tip_rect
        return x0 <= x <= x1 and y0 <= y <= y1

    # ---------------- 边缘躲藏 ----------------
    def _head_rect(self) -> tuple[float, float, float, float]:
        """脑袋（伞盖）在窗口坐标里的大致矩形。"""
        return head_rect(self.scale)

    def _dock_pos(self, edge: str, revealed: bool) -> tuple[int, int]:
        """计算躲到某条边时的窗口位置（窗口坐标->屏幕）。"""
        hx0, hy0, hx1, hy1 = self._head_rect()
        head_w = hx1 - hx0
        head_h = hy1 - hy0
        r = work_area()
        x, y = self.pos
        if edge in ("left", "right"):
            peek = max(4.0, EDGE_PEEK_SIDE * head_w)
            y = max(r.top - hy0, min(y, r.bottom - hy1))
        else:
            frac = EDGE_PEEK_TOP if edge == "top" else EDGE_PEEK
            peek = max(4.0, frac * head_h)
            x = max(r.left - hx0, min(x, r.right - hx1))

        if edge == "bottom":
            y = r.bottom + peek - hy1
            if revealed:
                x = max(r.left - hx0, min(x, r.right - hx1))
                y = r.bottom - hy1
        elif edge == "top":
            y = r.top - peek - hy0
            if revealed:
                x = max(r.left - hx0, min(x, r.right - hx1))
                y = r.top - hy0
        elif edge == "left":
            x = r.left - peek - hx0
            if revealed:
                y = max(r.top - hy0, min(y, r.bottom - hy1))
                x = r.left - hx0
        else:  # right
            x = r.right + peek - hx1
            if revealed:
                y = max(r.top - hy0, min(y, r.bottom - hy1))
                x = r.right - hx1
        return int(round(x)), int(round(y))

    def _nearest_edge(self) -> str | None:
        """脑袋离哪条边最近；不在吸附半径内则返回 None。"""
        hx0, hy0, hx1, hy1 = self._head_rect()
        sx0 = self.pos[0] + hx0
        sy0 = self.pos[1] + hy0
        sx1 = self.pos[0] + hx1
        sy1 = self.pos[1] + hy1
        r = work_area()
        dists = {
            "left": sx0 - r.left,
            "right": r.right - sx1,
            "top": sy0 - r.top,
            "bottom": r.bottom - sy1,
        }
        edge = min(dists, key=dists.get)
        if dists[edge] > EDGE_SNAP_RADIUS * self.dpi_scale:
            return None
        return edge

    def _move_window(self, x: int, y: int) -> None:
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST if self.topmost else ctypes.c_void_p(0),
            int(x), int(y), 0, 0, SWP_NOSIZE | SWP_NOACTIVATE,
        )

    def _step_anim(self) -> None:
        if self.anim_target is None or self.dragging:
            return
        tx, ty = self.anim_target
        x, y = self.pos
        if abs(tx - x) <= 1 and abs(ty - y) <= 1:
            self.pos = [tx, ty]
            self.anim_target = None
            self._move_window(tx, ty)
            return
        nx = int(round(x + (tx - x) * 0.35))
        ny = int(round(y + (ty - y) * 0.35))
        self.pos = [nx, ny]
        self._move_window(nx, ny)

    def _update_dock(self) -> None:
        if self.dragging or self.dock_edge is None:
            return
        now = time.monotonic()
        if self.hidden:
            if self.hover and self.reveal_armed:
                self.hidden = False
                self.reveal = True
                self.redock_at = 0.0
                self.anim_target = self._dock_pos(self.dock_edge, revealed=True)
            return
        if self.reveal:
            # 已经探出来：鼠标离开一段时间后重新躲回去
            if self.hover:
                self.redock_at = 0.0
            elif self.redock_at == 0.0:
                self.redock_at = now + REDOCK_DELAY
            elif now >= self.redock_at:
                self.reveal = False
                self.redock_at = 0.0
                self.anim_target = self._dock_pos(self.dock_edge, revealed=False)
            return
        # 正在回缩：动画结束就只留脑袋
        if self.anim_target is None:
            self.hidden = True

    def _clip_to_work_area(self, img: Image.Image) -> Image.Image:
        """把窗口伸出工作区（任务栏区域）的部分裁成透明。"""
        r = work_area()
        x0 = r.left - self.pos[0]
        y0 = r.top - self.pos[1]
        x1 = r.right - self.pos[0]
        y1 = r.bottom - self.pos[1]
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

    def _finish_drag(self) -> None:
        """拖拽结束：靠近边缘就躲起来，否则保持悬浮。"""
        edge = self._nearest_edge()
        self.reveal_armed = False
        self.hidden = False
        self.reveal = False
        self.redock_at = 0.0
        if edge is not None:
            self.dock_edge = edge
            self.anim_target = self._dock_pos(edge, revealed=False)
            self.cfg["dock"] = edge
            self.cfg["x"], self.cfg["y"] = self._dock_pos(edge, revealed=True)
        else:
            self.dock_edge = None
            self.anim_target = None
            self.cfg["dock"] = None
            self.pos[0], self.pos[1] = clamp_head(
                self.pos[0], self.pos[1], self._head_rect()
            )
            self._move_window(*self.pos)
            self.cfg["x"], self.cfg["y"] = self.pos
        save_config(self.cfg)
        log(f"drag end edge={edge} pos={self.pos}")
        self._render()

    # ---------------- 终端控制 ----------------
    def _remember_terminal(self, hwnd: int) -> None:
        """把水母打开过的终端窗口记到最前面并持久化。"""
        if hwnd <= 0:
            return
        self.term_history = [hwnd] + [h for h in self.term_history if h != hwnd]
        del self.term_history[8:]
        self.cfg["term_hwnds"] = list(self.term_history)
        save_config(self.cfg)

    def _adopt_terminal(self) -> bool:
        """当前终端窗口已经关闭时，接管最近打开且仍然存在的那个。"""
        before = self.term_hwnd
        live = [h for h in self.term_history if is_terminal_window(h)]
        if live != self.term_history:
            self.term_history = live
            self.cfg["term_hwnds"] = list(live)
            save_config(self.cfg)
        if not self.term_history:
            return False
        self.term_hwnd = self.term_history[0]
        if self.term_hwnd != before:
            log(f"adopt terminal hwnd={self.term_hwnd}")
        return True

    def _toggle_terminal(self) -> None:
        if self.launching:
            return
        h = self.term_hwnd
        if not (h and user32.IsWindow(h)):
            self.term_hwnd = 0
            if not self._adopt_terminal():
                self._launch_terminal()
                self._render()
                return
            h = self.term_hwnd
        if user32.IsWindowVisible(h) and not user32.IsIconic(h):
            user32.ShowWindow(h, SW_HIDE)
            log("terminal hidden")
        else:
            self._show_terminal()
        self._render()

    def _show_terminal(self) -> None:
        h = self.term_hwnd
        if not h or not user32.IsWindow(h):
            return
        if user32.IsIconic(h):
            user32.ShowWindow(h, SW_RESTORE)
        else:
            user32.ShowWindow(h, SW_SHOW)
        force_foreground(h)
        log("terminal shown")

    def _launch_terminal(self, continue_last: bool = False) -> None:
        if self.launching:
            return
        self.launching = True
        self.error_until = 0.0
        threading.Thread(
            target=self._launch_worker, args=(continue_last,), daemon=True
        ).start()
        self._render()

    def _launch_worker(self, continue_last: bool) -> None:
        try:
            before = {h for h, _ in list_terminal_windows()}
            script = self._write_launch_script(continue_last)
            args = [
                WT, "-w", "new", "--title", TERM_TITLE,
                "cmd.exe", "/d", "/k", str(script),
            ]
            log("launch: " + " ".join(f'"{a}"' if " " in a else a for a in args))
            log(f"launch provider={self.provider}")
            subprocess.Popen(
                args,
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            found = 0
            deadline = time.time() + 12.0
            while time.time() < deadline and not found:
                time.sleep(0.15)
                try:
                    wins = list_terminal_windows()
                except Exception:
                    continue
                new = [(h, t) for h, t in wins if h not in before]
                if new:
                    for h, t in new:
                        if TERM_TITLE.lower() in t.lower():
                            found = h
                            break
                    if not found:
                        found = new[-1][0]
            if found:
                self.term_hwnd = found
                self._remember_terminal(found)
                log(f"terminal found hwnd={found}")
                user32.PostMessageW(self.hwnd, WM_APP_LAUNCHED, 0, 0)
            else:
                log("terminal window not found")
                self.error_until = time.monotonic() + 4.0
        except Exception:
            log("launch failed\n" + traceback.format_exc())
            self.error_until = time.monotonic() + 4.0
        finally:
            self.launching = False
            try:
                user32.PostMessageW(self.hwnd, WM_APP_LAUNCHED, 0, 0)
            except Exception:
                pass

    def _restart_terminal(self) -> None:
        h = self.term_hwnd
        if h and user32.IsWindow(h):
            user32.PostMessageW(h, WM_CLOSE, 0, 0)
        self.term_hwnd = 0
        self.launching = False
        self._launch_terminal()

    # ---------------- 大模型接口 ----------------
    def _provider_values(self, provider: str) -> tuple[str, str, str]:
        """返回某个接口的 (接口地址, 模型名称, API Key)。"""
        return provider_values(provider, self.provider_cfg)

    def _write_launch_script(self, continue_last: bool) -> Path:
        """生成启动脚本，用 --settings 指定本次会话的模型接口。"""
        return write_launch_script(
            self.provider, self.provider_cfg, continue_last
        )

    def _prompt_provider_config(
        self, provider: str, base_url: str, model: str, api_key: str
    ) -> dict[str, str] | None:
        """弹出配置窗口，返回 {base_url, model, api_key}；取消返回 None。"""
        try:
            import tkinter as tk
            from tkinter import messagebox
        except Exception:
            log("tkinter unavailable\n" + traceback.format_exc())
            return None

        root = tk.Tk()
        root.title(f"{APP_NAME} - {PROVIDER_LABELS[provider]}")
        root.resizable(False, False)
        root.attributes("-topmost", True)

        url_var = tk.StringVar(value=base_url)
        model_var = tk.StringVar(value=model)
        key_var = tk.StringVar(value=api_key)
        show_key = tk.BooleanVar(value=False)
        result: dict[str, str] | None = None

        for row, (text, var) in enumerate(
            (("接口地址", url_var), ("模型名称", model_var))
        ):
            pad = (12 if row == 0 else 6, 0)
            tk.Label(root, text=text).grid(
                row=row, column=0, sticky="w", padx=12, pady=pad
            )
            tk.Entry(root, textvariable=var, width=48).grid(
                row=row, column=1, padx=12, pady=pad
            )

        tk.Label(root, text="API Key").grid(
            row=2, column=0, sticky="w", padx=12, pady=6
        )
        key_entry = tk.Entry(root, textvariable=key_var, width=48, show="*")
        key_entry.grid(row=2, column=1, padx=12, pady=6)

        def toggle_key() -> None:
            key_entry.configure(show="" if show_key.get() else "*")

        tk.Checkbutton(
            root, text="显示 API Key", variable=show_key, command=toggle_key
        ).grid(row=3, column=1, sticky="w", padx=8)

        def on_ok() -> None:
            nonlocal result
            url = url_var.get().strip()
            mdl = model_var.get().strip()
            key = key_var.get().strip()
            if not url or not mdl:
                messagebox.showwarning(
                    "设置", "接口地址和模型名称不能为空。", parent=root
                )
                return
            try:
                for value in (url, mdl, key):
                    bat_value(value)
            except ValueError as exc:
                messagebox.showwarning("设置", str(exc), parent=root)
                return
            result = {"base_url": url, "model": mdl, "api_key": key}
            root.destroy()

        buttons = tk.Frame(root)
        buttons.grid(row=4, column=0, columnspan=2, pady=12)
        tk.Button(buttons, text="取消", width=10, command=root.destroy).pack(
            side="right", padx=(8, 12)
        )
        tk.Button(buttons, text="保存", width=10, command=on_ok).pack(
            side="right"
        )

        root.bind("<Return>", lambda _e: on_ok())
        root.bind("<Escape>", lambda _e: root.destroy())
        root.update_idletasks()
        w, h = root.winfo_width(), root.winfo_height()
        x = (root.winfo_screenwidth() - w) // 2
        y = (root.winfo_screenheight() - h) // 2
        root.geometry(f"+{x}+{y}")
        root.lift()
        root.focus_force()
        root.mainloop()
        return result

    def _select_provider(self, provider: str) -> None:
        if provider not in PROVIDER_ORDER:
            return
        if provider != "default":
            conf = self.provider_cfg.get(provider, {})
            needs_setup = not conf or (
                provider == "deepseek" and not conf.get("api_key")
            )
            if needs_setup:
                base_url, model, api_key = self._provider_values(provider)
                # 从当前进程或 Claude Code 的设置里预填，方便已经配好的人
                claude_env = read_claude_env()
                env_url = (
                    os.environ.get("ANTHROPIC_BASE_URL")
                    or claude_env.get("ANTHROPIC_BASE_URL", "")
                )
                if provider == "deepseek" and "deepseek" in env_url.lower():
                    base_url = base_url or env_url
                    model = model or (
                        os.environ.get("ANTHROPIC_MODEL")
                        or claude_env.get("ANTHROPIC_MODEL", "")
                    )
                    api_key = api_key or (
                        os.environ.get("ANTHROPIC_AUTH_TOKEN")
                        or claude_env.get("ANTHROPIC_AUTH_TOKEN", "")
                    )
                conf = self._prompt_provider_config(
                    provider, base_url, model, api_key
                )
                if conf is None:
                    return
                self.provider_cfg[provider] = conf
        self.provider = provider
        self.cfg["provider"] = provider
        self.cfg["providers"] = self.provider_cfg
        save_config(self.cfg)
        log(f"provider={provider}")

    def _edit_provider_config(self) -> None:
        if self.provider == "default":
            return
        base_url, model, api_key = self._provider_values(self.provider)
        conf = self._prompt_provider_config(
            self.provider, base_url, model, api_key
        )
        if conf is None:
            return
        self.provider_cfg[self.provider] = conf
        self.cfg["providers"] = self.provider_cfg
        save_config(self.cfg)
        log(f"provider config edited: {self.provider}")

    def _open_config(self) -> None:
        save_config(self.cfg)
        try:
            subprocess.Popen(["notepad.exe", str(CONFIG_PATH)])
        except Exception:
            log("open config failed\n" + traceback.format_exc())

    # ---------------- 交互 ----------------
    def _drag_move(self) -> None:
        p = wt.POINT()
        user32.GetCursorPos(ctypes.byref(p))
        dx = p.x - self.drag_cursor[0]
        dy = p.y - self.drag_cursor[1]
        if abs(dx) + abs(dy) > 4 and not self.drag_moved:
            self.drag_moved = True
            self.anim_target = None
            self.dock_edge = None
            self.reveal = False
            self.hidden = False
        nx = self.drag_origin[0] + dx
        ny = self.drag_origin[1] + dy
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST if self.topmost else ctypes.c_void_p(0),
            nx, ny, 0, 0, SWP_NOSIZE | SWP_NOACTIVATE,
        )
        self.pos = [nx, ny]

    def _update_hover(self) -> None:
        p = wt.POINT()
        user32.GetCursorPos(ctypes.byref(p))
        c = wt.POINT(p.x, p.y)
        user32.ScreenToClient(self.hwnd, ctypes.byref(c))
        inside = self._is_hit(c.x, c.y) or self._in_tooltip(c.x, c.y)
        # 探出来之后，只要鼠标还在水母身体范围内就保持展开，避免窗口移动造成抖动
        if not inside and self.dock_edge is not None and not self.hidden:
            bx0, by0, bx1, by1 = body_rect(self.scale)
            inside = bx0 <= c.x <= bx1 and by0 <= c.y <= by1
        now = time.monotonic()
        self.hover = inside
        if inside:
            if self.hover_since == 0.0:
                self.hover_since = now
        else:
            self.hover_since = 0.0
            self.tip_shown = False
            self.reveal_armed = True
        if self.hover_since and now - self.hover_since > 0.45:
            self.tip_shown = True

    def _tick(self) -> None:
        h = self.term_hwnd
        if h and not user32.IsWindow(h):
            self.term_hwnd = 0
        if not self.term_hwnd:
            self._adopt_terminal()
            h = self.term_hwnd
        if h and user32.IsWindowVisible(h) and user32.IsIconic(h):
            user32.ShowWindow(h, SW_HIDE)
            log("auto-collapse on minimize")
        self._update_hover()
        self._update_dock()
        self._step_anim()
        target = 255.0 if self.hover else 255.0 * self.idle_opacity
        self.vis_alpha += (target - self.vis_alpha) * 0.28
        if abs(target - self.vis_alpha) < 1.0:
            self.vis_alpha = target
        self._render()

    def _apply_size(self, factor: float) -> None:
        self.size_factor = factor
        self.scale = self.dpi_scale * factor
        self.pw = max(1, int(round(BASE_W * self.scale)))
        self.ph = max(1, int(round(BASE_H * self.scale)))
        self.anim_target = None
        if self.dock_edge:
            self.hidden = not self.reveal
            self.pos = list(
                self._dock_pos(self.dock_edge, revealed=self.reveal)
            )
        else:
            self.pos[0], self.pos[1] = clamp_head(
                self.pos[0], self.pos[1], self._head_rect()
            )
        clear_sprite_cache()
        user32.SetWindowPos(
            self.hwnd, None, self.pos[0], self.pos[1], self.pw, self.ph,
            SWP_NOZORDER | SWP_NOACTIVATE,
        )
        self.cfg["size"] = factor
        save_config(self.cfg)
        self._render()

    def _apply_opacity(self, value: float) -> None:
        self.idle_opacity = value
        self.cfg["opacity"] = value
        save_config(self.cfg)
        self._render()

    def _apply_float(self, speed: float) -> None:
        if abs(speed - self.float_speed) < 0.001:
            return
        # 调整相位偏移，避免切换速度时动画跳一下
        elapsed = time.monotonic() - self.t0
        self.anim_offset += elapsed * (self.float_speed - speed)
        self.float_speed = speed
        self.cfg["float_speed"] = speed
        save_config(self.cfg)
        self._render()

    def _toggle_tip(self) -> None:
        self.show_tip = not self.show_tip
        self.cfg["show_tip"] = self.show_tip
        save_config(self.cfg)
        if not self.show_tip:
            self.tip_shown = False
        self._render()

    def _toggle_topmost(self) -> None:
        self.topmost = not self.topmost
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST if self.topmost else HWND_NOTOPMOST,
            0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE,
        )
        self.cfg["topmost"] = self.topmost
        save_config(self.cfg)

    def _show_menu(self, sx: int, sy: int) -> None:
        state = self._state()
        menu = user32.CreatePopupMenu()
        size_menu = user32.CreatePopupMenu()
        opacity_menu = user32.CreatePopupMenu()
        float_menu = user32.CreatePopupMenu()
        settings_menu = user32.CreatePopupMenu()
        provider_menu = user32.CreatePopupMenu()
        try:
            toggle_label = "收起 Claude Code" if state == "visible" else "打开 Claude Code"
            user32.AppendMenuW(menu, MF_STRING, 100, toggle_label)
            user32.AppendMenuW(
                menu,
                MF_STRING | (MF_GRAYED if state in ("visible", "hidden") else 0),
                101, "继续上次会话",
            )
            user32.AppendMenuW(
                menu,
                MF_STRING | (MF_GRAYED if state not in ("visible", "hidden") else 0),
                102, "重新开始会话",
            )
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

            for i, v in enumerate(SIZE_PRESETS):
                flags = MF_STRING
                if abs(self.size_factor - v) < 0.001:
                    flags |= MF_CHECKED
                user32.AppendMenuW(size_menu, flags, 200 + i,
                                   f"{int(round(v * 100))}%")
            user32.AppendMenuW(menu, MF_POPUP, size_menu, "大小")

            for i, v in enumerate(OPACITY_PRESETS):
                flags = MF_STRING
                if abs(self.idle_opacity - v) < 0.001:
                    flags |= MF_CHECKED
                user32.AppendMenuW(opacity_menu, flags, 300 + i,
                                   f"{int(round(v * 100))}%")
            user32.AppendMenuW(menu, MF_POPUP, opacity_menu, "透明度")

            for i, speed in enumerate(FLOAT_PRESETS):
                flags = MF_STRING
                if abs(self.float_speed - speed) < 0.001:
                    flags |= MF_CHECKED
                user32.AppendMenuW(float_menu, flags, 400 + i,
                                   FLOAT_LABELS[i])
            user32.AppendMenuW(menu, MF_POPUP, float_menu, "浮动频率")

            for i, name in enumerate(PROVIDER_ORDER):
                flags = MF_STRING
                if self.provider == name:
                    flags |= MF_CHECKED
                user32.AppendMenuW(provider_menu, flags, 500 + i,
                                   PROVIDER_LABELS[name])
            user32.AppendMenuW(settings_menu, MF_POPUP, provider_menu,
                               "大模型接口")
            user32.AppendMenuW(settings_menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(
                settings_menu,
                MF_STRING | (MF_GRAYED if self.provider == "default" else 0),
                510, "接口配置…",
            )
            user32.AppendMenuW(settings_menu, MF_STRING, 511, "打开配置文件")
            user32.AppendMenuW(menu, MF_POPUP, settings_menu, "设置")

            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(
                menu, MF_STRING | (MF_CHECKED if self.topmost else 0),
                103, "始终置顶",
            )
            user32.AppendMenuW(
                menu, MF_STRING | (MF_CHECKED if shortcut_exists() else 0),
                104, "开机自启",
            )
            user32.AppendMenuW(
                menu, MF_STRING | (MF_CHECKED if self.show_tip else 0),
                106, "显示文字提示",
            )
            user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(menu, MF_STRING, 105, "退出")

            user32.SetForegroundWindow(self.hwnd)
            cmd = user32.TrackPopupMenu(
                menu,
                TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_NONOTIFY,
                sx, sy, 0, self.hwnd, None,
            )
            user32.PostMessageW(self.hwnd, WM_NULL, 0, 0)
        finally:
            user32.DestroyMenu(menu)

        if cmd == 100:
            self._toggle_terminal()
        elif cmd == 101:
            self._launch_terminal(continue_last=True)
        elif cmd == 102:
            self._restart_terminal()
        elif cmd == 103:
            self._toggle_topmost()
        elif cmd == 104:
            set_autostart(not shortcut_exists())
        elif cmd == 105:
            self._quit()
        elif cmd == 106:
            self._toggle_tip()
        elif 200 <= cmd < 200 + len(SIZE_PRESETS):
            self._apply_size(SIZE_PRESETS[cmd - 200])
        elif 300 <= cmd < 300 + len(OPACITY_PRESETS):
            self._apply_opacity(OPACITY_PRESETS[cmd - 300])
        elif 400 <= cmd < 400 + len(FLOAT_PRESETS):
            self._apply_float(FLOAT_PRESETS[cmd - 400])
        elif 500 <= cmd < 500 + len(PROVIDER_ORDER):
            self._select_provider(PROVIDER_ORDER[cmd - 500])
        elif cmd == 510:
            self._edit_provider_config()
        elif cmd == 511:
            self._open_config()

    def _quit(self) -> None:
        if self.dock_edge:
            self.cfg["x"], self.cfg["y"] = self._dock_pos(
                self.dock_edge, revealed=True
            )
        else:
            self.cfg["x"], self.cfg["y"] = self.pos
        self.cfg["dock"] = self.dock_edge
        self.cfg["size"] = self.size_factor
        self.cfg["opacity"] = self.idle_opacity
        self.cfg["float_speed"] = self.float_speed
        self.cfg["show_tip"] = self.show_tip
        save_config(self.cfg)
        user32.UnregisterHotKey(self.hwnd, HOTKEY_ID)
        user32.DestroyWindow(self.hwnd)

    # ---------------- 窗口过程 ----------------
    def _wndproc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_NCHITTEST:
                sx = ctypes.c_short(lparam & 0xFFFF).value
                sy = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                p = wt.POINT(sx, sy)
                user32.ScreenToClient(hwnd, ctypes.byref(p))
                if self.dragging or self._is_hit(p.x, p.y):
                    return HTCLIENT
                return HTTRANSPARENT

            if msg == WM_MOUSEMOVE:
                if self.dragging:
                    self._drag_move()
                return 0

            if msg == WM_LBUTTONDOWN:
                x = ctypes.c_short(lparam & 0xFFFF).value
                y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                if not self._is_hit(x, y):
                    return 0
                self.anim_target = None
                if self.dock_edge is not None:
                    # 按住躲藏中的水母先把它探出来
                    self.hidden = False
                    self.reveal = True
                    self.redock_at = 0.0
                    self.anim_target = self._dock_pos(
                        self.dock_edge, revealed=True
                    )
                self.dragging = True
                self.drag_moved = False
                p = wt.POINT()
                user32.GetCursorPos(ctypes.byref(p))
                self.drag_cursor = (p.x, p.y)
                r = wt.RECT()
                user32.GetWindowRect(hwnd, ctypes.byref(r))
                self.drag_origin = (r.left, r.top)
                user32.SetCapture(hwnd)
                return 0

            if msg == WM_LBUTTONUP:
                if self.dragging:
                    self.dragging = False
                    user32.ReleaseCapture()
                    if self.drag_moved:
                        self._finish_drag()
                    else:
                        self._toggle_terminal()
                return 0

            if msg == WM_RBUTTONUP:
                x = ctypes.c_short(lparam & 0xFFFF).value
                y = ctypes.c_short((lparam >> 16) & 0xFFFF).value
                if not self._is_hit(x, y):
                    return 0
                p = wt.POINT(x, y)
                user32.ClientToScreen(hwnd, ctypes.byref(p))
                self._show_menu(p.x, p.y)
                return 0

            if msg == WM_TIMER:
                self._tick()
                return 0

            if msg == WM_HOTKEY:
                if wparam == HOTKEY_ID:
                    self._toggle_terminal()
                return 0

            if msg == WM_APP_LAUNCHED:
                if self.term_hwnd and user32.IsWindow(self.term_hwnd):
                    self._show_terminal()
                self._render()
                return 0

            if msg == self.toggle_msg:
                self._toggle_terminal()
                return 0

            if msg == WM_ERASEBKGND:
                return 1

            if msg == WM_CLOSE:
                self._quit()
                return 0

            if msg == WM_DESTROY:
                user32.KillTimer(hwnd, 1)
                user32.UnregisterHotKey(hwnd, HOTKEY_ID)
                user32.PostQuitMessage(0)
                return 0

        except Exception:
            log("wndproc error\n" + traceback.format_exc())

        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)



# --------------------------------------------------------------------------
# 入口
# --------------------------------------------------------------------------
def _single_instance_guard() -> bool:
    handle = kernel32.CreateMutexW(None, False, "Local\\ClaudeJelly_SingleInstance")
    if not handle:
        return True
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        msg = user32.RegisterWindowMessageW("ClaudeJelly_Toggle_v1")
        user32.PostMessageW(ctypes.c_void_p(0xFFFF), msg, 0, 0)  # HWND_BROADCAST
        return False
    globals()["_MUTEX_HANDLE"] = handle
    return True


def preview(args: list[str]) -> None:
    scale = 2.0
    if "--scale" in args:
        try:
            scale = float(args[args.index("--scale") + 1])
        except Exception:
            pass
    t = 1.37
    variants = [
        ("preview_light.png", False, False, "打开 Claude Code", "none", 0),
        ("preview_hover.png", True, True, "打开 Claude Code", "none", 0),
        ("preview_active.png", True, True, "收起窗口", "visible", -1),
        ("preview_bubbles.png", True, True, "收起窗口", "visible", 1),
    ]
    out_dir = LOCAL_DIR / "previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, hover, tip, text, state, bdir in variants:
        img, _ = draw_frame(scale, t, hover, tip, text, state, False, bdir)
        light = Image.new("RGBA", img.size, (238, 239, 242, 255))
        light.alpha_composite(img)
        light.convert("RGB").save(out_dir / name)
    img, _ = draw_frame(scale, t, True, True, "打开 Claude Code", "none")
    dark = Image.new("RGBA", img.size, (32, 32, 34, 255))
    dark.alpha_composite(img)
    dark.convert("RGB").save(out_dir / "preview_dark.png")
    img, _ = draw_frame(scale, t, False, False, "", "none", True)
    light = Image.new("RGBA", img.size, (238, 239, 242, 255))
    light.alpha_composite(img)
    light.convert("RGB").save(out_dir / "preview_hidden.png")
    print(f"previews written to {out_dir}")


def main() -> None:
    args = sys.argv[1:]
    if "--preview" in args:
        preview(args)
        return

    enable_dpi_awareness()
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    if not _single_instance_guard():
        return

    app = JellyApp()
    log(f"started pid={os.getpid()} scale={app.scale} claude={CLAUDE} wt={WT}")
    app.run()


def preview_cli() -> None:
    """`claude-jelly-preview` 命令入口，把预览图输出到本机配置目录。"""
    preview(sys.argv[1:])
