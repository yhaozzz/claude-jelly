"""JellyApp：组装窗口、绘制、终端会话与交互状态。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import math
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path

from .config import (
    APP_NAME,
    CLAUDE,
    CONFIG_PATH,
    LOCAL_DIR,
    WT,
    load_config,
    log,
    save_config,
)
from .controllers import docking
from .controllers.terminal import TerminalSession
from .services.autostart import set_autostart, shortcut_exists
from .services.providers import (
    PROVIDER_DEFAULTS,
    PROVIDER_ORDER,
    provider_values,
    read_claude_env,
)
from .ui.menu import (
    CMD_AUTOSTART,
    CMD_CONTINUE,
    CMD_EDIT_PROVIDER,
    CMD_FLOAT,
    CMD_OPACITY,
    CMD_OPEN_CONFIG,
    CMD_PICK_SPRITE,
    CMD_PROVIDER,
    CMD_QUIT,
    CMD_RESET_SPRITE,
    CMD_RESTART,
    CMD_SIZE,
    CMD_TIP,
    CMD_TOGGLE,
    CMD_TOPMOST,
    FLOAT_PRESETS,
    OPACITY_PRESETS,
    SIZE_PRESETS,
    MenuState,
    show_context_menu,
)
from .ui.provider_dialog import prompt_provider_config
from .ui.render import (
    BASE_H,
    BASE_W,
    BUBBLE_EXIT_OFFSET,
    BUBBLE_PAD,
    BUBBLE_RISE,
    RUNNING_STATES,
    SPRITE_CY,
    body_rect,
    clear_sprite_cache,
    draw_frame,
    head_rect,
    set_sprite_image,
)
from .ui.render.preview import preview
from .ui.window import LayeredWindow, clip_to_work_area
from .winapi.bindings import (
    ERROR_ALREADY_EXISTS,
    HOTKEY_ID,
    HTCLIENT,
    HTTRANSPARENT,
    MOD_ALT,
    MOD_CONTROL,
    MOD_NOREPEAT,
    MWMO_INPUTAVAILABLE,
    PM_REMOVE,
    QS_ALLINPUT,
    WM_APP_LAUNCHED,
    WM_CLOSE,
    WM_DESTROY,
    WM_ERASEBKGND,
    WM_HOTKEY,
    WM_LBUTTONDOWN,
    WM_LBUTTONUP,
    WM_MOUSEMOVE,
    WM_NCHITTEST,
    WM_QUIT,
    WM_RBUTTONUP,
    WM_TIMER,
    kernel32,
    user32,
    winmm,
)
from .winapi.dialogs import pick_image_file
from .winapi.screen import clamp_head, enable_dpi_awareness, work_area

# 动画刷新间隔（毫秒）：16ms ≈ 60 FPS，配合 winmm.timeBeginPeriod(1) 才不会被系统拉长
FRAME_MS = 16
# 兜底定时器：右键菜单 / 文件对话框会自己跑消息循环，主循环被挡住时靠它补帧
FALLBACK_TIMER_MS = 100
FALLBACK_TICK_GAP = 0.05
# 缓动的时间常数（秒）。和帧率无关，所以调高帧率不会让动画变快/变慢
HOVER_IN_TAU = 0.07    # 悬停淡入：快一点，点了就有反应
HOVER_OUT_TAU = 0.16   # 离开淡出：慢一点，不闪


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
        # ---- 悬浮形象：默认水母 / 用户自选图片 ----
        self.sprite_path = ""
        saved_sprite = self.cfg.get("sprite")
        if isinstance(saved_sprite, str) and saved_sprite:
            if Path(saved_sprite).is_file() and set_sprite_image(saved_sprite):
                self.sprite_path = saved_sprite
                log(f"sprite={saved_sprite}")
            else:
                log(f"sprite missing: {saved_sprite}")

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

        # ---- 窗口与绘制状态 ----
        self.window: LayeredWindow | None = None
        self.hwnd: int = 0
        self.tip_rect: tuple[int, int, int, int] | None = None
        self.t0 = time.monotonic()
        self.last_tick = self.t0
        self.frame_sig: tuple | None = None
        self.hover = False
        self.vis_alpha = 255.0 * self.idle_opacity
        self.hover_since = 0.0
        self.tip_shown = False
        self.dragging = False
        self.drag_moved = False
        self.drag_cursor = (0, 0)
        self.drag_origin = (0, 0)

        # ---- 终端会话 ----
        raw_history = self.cfg.get("term_hwnds", [])
        if not isinstance(raw_history, list):
            raw_history = []
        self.terminal = TerminalSession(
            raw_history, self._notify_launched, self._persist_terminal_history
        )

        self.toggle_msg = user32.RegisterWindowMessageW("ClaudeJelly_Toggle_v1")
        self.window = LayeredWindow(
            self._wndproc, (self.pos[0], self.pos[1]),
            self.pw, self.ph, self.topmost,
        )
        self.hwnd = self.window.hwnd
        self._render()
        self.window.show()
        user32.SetTimer(self.hwnd, 1, FALLBACK_TIMER_MS, None)

        ok = user32.RegisterHotKey(
            self.hwnd, HOTKEY_ID,
            MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("J"),
        )
        log(f"hotkey registered: {bool(ok)}")

    # ---------------- 消息循环 ----------------
    def run(self) -> None:
        msg = wt.MSG()
        interval = FRAME_MS / 1000.0
        next_tick = time.monotonic() + interval
        while True:
            # 用等待超时来计时，不用 WM_TIMER：Windows 会把短间隔的 SetTimer
            # 合并到 ~15.6ms 的边界上，16ms 的定时器实际只有 ~31ms 才触发一次
            timeout = next_tick - time.monotonic()
            if timeout > 0:
                user32.MsgWaitForMultipleObjectsEx(
                    0, None, int(timeout * 1000.0) + 1, QS_ALLINPUT,
                    MWMO_INPUTAVAILABLE,
                )
            else:
                self._tick()
                now = time.monotonic()
                next_tick += interval
                if next_tick <= now:
                    # 掉帧了：重新对齐，别连着补好几帧
                    next_tick = now + interval
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                if msg.message == WM_QUIT:
                    return
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

    # ---------------- 状态 ----------------
    def _state(self) -> str:
        return self.terminal.state()

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

    # ---------------- 绘制 ----------------
    def _render(self) -> None:
        if not self.hwnd:
            return
        t = (time.monotonic() - self.t0) * self.float_speed + self.anim_offset
        state = self._state()
        # 贴在上边缘：不吐泡泡，改成挂着晃触手（Claude Code 在运行时才晃）
        hanging = self.dock_edge == "top"
        tip_on = self.tip_shown and self.show_tip
        tip_text = self._tip_text(state)
        body_hidden = self.hidden and not hanging
        bubble_dir = 0 if hanging else self._focus_side()
        bubble_low = self._bubble_low()
        hang_sway = hanging and state in RUNNING_STATES
        # 画面完全没变化时不必重画（比如“静止”悬浮速度下）：
        # 省 CPU，也避免同一帧反复交给 UpdateLayeredWindow
        sig = (
            round(t, 4), state, self.hover, tip_on, tip_text, body_hidden,
            bubble_dir, bubble_low, hang_sway, self.vis_alpha,
            self.pos[0], self.pos[1], self.scale, self.sprite_path,
        )
        if sig == self.frame_sig:
            return
        self.frame_sig = sig
        img, tip_rect = draw_frame(
            self.scale, t, self.hover, tip_on, tip_text, state,
            body_hidden, bubble_dir, bubble_low, hang_sway,
        )
        img = clip_to_work_area(img, (self.pos[0], self.pos[1]))
        self.tip_rect = tip_rect
        self.window.paint(img, self.vis_alpha)

    def _alpha_at(self, x: int, y: int) -> int:
        return self.window.alpha_at(x, y)

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
        return docking.dock_pos(
            edge, (self.pos[0], self.pos[1]), self._head_rect(),
            work_area(), revealed,
        )

    def _nearest_edge(self) -> str | None:
        """脑袋离哪条边最近；不在吸附半径内则返回 None。"""
        return docking.nearest_edge(
            (self.pos[0], self.pos[1]), self._head_rect(), work_area(),
            docking.EDGE_SNAP_RADIUS * self.dpi_scale,
        )

    def _move_window(self, x: int, y: int) -> None:
        self.window.move(x, y, self.topmost)

    def _step_anim(self, dt: float) -> None:
        if self.anim_target is None or self.dragging:
            return
        new_pos, done = docking.ease_towards(
            (self.pos[0], self.pos[1]), self.anim_target, dt
        )
        self.pos = [new_pos[0], new_pos[1]]
        self._move_window(*self.pos)
        if done:
            self.anim_target = None

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
                self.redock_at = now + docking.REDOCK_DELAY
            elif now >= self.redock_at:
                self.reveal = False
                self.redock_at = 0.0
                self.anim_target = self._dock_pos(self.dock_edge, revealed=False)
            return
        # 正在回缩：动画结束就只留脑袋
        if self.anim_target is None:
            self.hidden = True

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
            self.pos[0], self.pos[1] = clamp_head(
                self.pos[0], self.pos[1], self._head_rect()
            )
            self._move_window(*self.pos)
            self.cfg["x"], self.cfg["y"] = self.pos
        save_config(self.cfg)
        log(f"drag end edge={edge} pos={self.pos}")
        self._render()

    # ---------------- 终端会话 ----------------
    def _notify_launched(self) -> None:
        user32.PostMessageW(self.hwnd, WM_APP_LAUNCHED, 0, 0)

    def _persist_terminal_history(self, history: list[int]) -> None:
        self.cfg["term_hwnds"] = list(history)
        save_config(self.cfg)

    def _toggle_terminal(self) -> None:
        if self.terminal.launching:
            return
        self.terminal.toggle(self.provider, self.provider_cfg)
        self._render()

    def _launch_terminal(self, continue_last: bool = False) -> None:
        if self.terminal.launching:
            return
        self.terminal.launch(self.provider, self.provider_cfg, continue_last)
        self._render()

    def _restart_terminal(self) -> None:
        self.terminal.restart(self.provider, self.provider_cfg)
        self._render()

    # ---------------- 大模型接口 ----------------
    def _provider_values(self, provider: str) -> tuple[str, str, str]:
        """返回某个接口的 (接口地址, 模型名称, API Key)。"""
        return provider_values(provider, self.provider_cfg)

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
                conf = prompt_provider_config(
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
        conf = prompt_provider_config(
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
        self.window.move(nx, ny, self.topmost)
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
        now = time.monotonic()
        dt = min(0.1, max(0.0, now - self.last_tick))
        self.last_tick = now
        self.terminal.poll()
        self._update_hover()
        self._update_dock()
        self._step_anim(dt)
        target = 255.0 if self.hover else 255.0 * self.idle_opacity
        tau = HOVER_IN_TAU if target > self.vis_alpha else HOVER_OUT_TAU
        self.vis_alpha += (target - self.vis_alpha) * (1.0 - math.exp(-dt / tau))
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
        self.window.set_bounds(
            self.pos[0], self.pos[1], self.pw, self.ph
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

    def _apply_sprite(self, path: str | None) -> bool:
        """切换悬浮形象：path=None 恢复默认水母，返回是否成功。"""
        if not set_sprite_image(path):
            return False
        self.sprite_path = str(path) if path else ""
        self.cfg["sprite"] = self.sprite_path
        save_config(self.cfg)
        # 图片宽高比可能不同，重新校正位置，避免脑袋出屏 / 躲藏错位
        self.anim_target = None
        if self.dock_edge:
            self.pos = list(
                self._dock_pos(self.dock_edge, revealed=self.reveal)
            )
        else:
            self.pos[0], self.pos[1] = clamp_head(
                self.pos[0], self.pos[1], self._head_rect()
            )
        self.window.set_bounds(
            self.pos[0], self.pos[1], self.pw, self.ph
        )
        self._render()
        log(f"sprite={self.sprite_path or '<default>'}")
        return True

    def _pick_sprite(self) -> None:
        initial = str(Path(self.sprite_path).parent) if self.sprite_path else ""
        path = pick_image_file(self.hwnd, "选择悬浮图片", initial)
        if not path:
            return
        if not self._apply_sprite(path):
            # MB_ICONWARNING
            user32.MessageBoxW(
                self.hwnd,
                "这个文件无法作为图片打开。\n"
                "支持 PNG / JPG / GIF / BMP / WebP。",
                APP_NAME, 0x30,
            )

    def _toggle_tip(self) -> None:
        self.show_tip = not self.show_tip
        self.cfg["show_tip"] = self.show_tip
        save_config(self.cfg)
        if not self.show_tip:
            self.tip_shown = False
        self._render()

    def _toggle_topmost(self) -> None:
        self.topmost = not self.topmost
        self.window.set_topmost(self.topmost)
        self.cfg["topmost"] = self.topmost
        save_config(self.cfg)

    # ---------------- 右键菜单 ----------------
    def _show_menu(self, sx: int, sy: int) -> None:
        state = MenuState(
            window_state=self._state(),
            size_factor=self.size_factor,
            idle_opacity=self.idle_opacity,
            float_speed=self.float_speed,
            provider=self.provider,
            sprite_path=self.sprite_path,
            topmost=self.topmost,
            autostart=shortcut_exists(),
            show_tip=self.show_tip,
        )
        cmd = show_context_menu(self.hwnd, sx, sy, state)
        self._handle_menu_command(cmd)

    def _handle_menu_command(self, cmd: int) -> None:
        if cmd == CMD_TOGGLE:
            self._toggle_terminal()
        elif cmd == CMD_CONTINUE:
            self._launch_terminal(continue_last=True)
        elif cmd == CMD_RESTART:
            self._restart_terminal()
        elif cmd == CMD_TOPMOST:
            self._toggle_topmost()
        elif cmd == CMD_AUTOSTART:
            set_autostart(not shortcut_exists())
        elif cmd == CMD_QUIT:
            self._quit()
        elif cmd == CMD_TIP:
            self._toggle_tip()
        elif CMD_SIZE <= cmd < CMD_SIZE + len(SIZE_PRESETS):
            self._apply_size(SIZE_PRESETS[cmd - CMD_SIZE])
        elif CMD_OPACITY <= cmd < CMD_OPACITY + len(OPACITY_PRESETS):
            self._apply_opacity(OPACITY_PRESETS[cmd - CMD_OPACITY])
        elif CMD_FLOAT <= cmd < CMD_FLOAT + len(FLOAT_PRESETS):
            self._apply_float(FLOAT_PRESETS[cmd - CMD_FLOAT])
        elif cmd == CMD_PICK_SPRITE:
            self._pick_sprite()
        elif cmd == CMD_RESET_SPRITE:
            self._apply_sprite(None)
        elif CMD_PROVIDER <= cmd < CMD_PROVIDER + len(PROVIDER_ORDER):
            self._select_provider(PROVIDER_ORDER[cmd - CMD_PROVIDER])
        elif cmd == CMD_EDIT_PROVIDER:
            self._edit_provider_config()
        elif cmd == CMD_OPEN_CONFIG:
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
        self.window.destroy()

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
                # 正常时主循环每 16ms tick 一次，这里只在被模态循环挡住时才补一帧
                if time.monotonic() - self.last_tick >= FALLBACK_TICK_GAP:
                    self._tick()
                return 0

            if msg == WM_HOTKEY:
                if wparam == HOTKEY_ID:
                    self._toggle_terminal()
                return 0

            if msg == WM_APP_LAUNCHED:
                if self.terminal.hwnd and user32.IsWindow(self.terminal.hwnd):
                    self.terminal.show()
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


def main() -> None:
    args = sys.argv[1:]
    if "--preview" in args:
        preview(args)
        return

    enable_dpi_awareness()
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)

    if not _single_instance_guard():
        return

    # 1ms 计时精度：消息循环的等待超时才准，16ms 一帧才能真正跑到 ~60FPS
    winmm.timeBeginPeriod(1)
    try:
        app = JellyApp()
        log(f"started pid={os.getpid()} scale={app.scale} claude={CLAUDE} wt={WT}")
        app.run()
    finally:
        winmm.timeEndPeriod(1)


def preview_cli() -> None:
    """`claude-jelly-preview` 命令入口，把预览图输出到本机配置目录。"""
    preview(sys.argv[1:])
