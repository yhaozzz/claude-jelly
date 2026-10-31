"""终端会话：Windows Terminal 的启动、收起、接管与运行状态。"""
from __future__ import annotations

import subprocess
import threading
import time
import traceback
from collections.abc import Callable

from ..config import TERM_TITLE, WT, log
from ..services.providers import write_launch_script
from ..winapi.bindings import (
    SW_HIDE,
    SW_RESTORE,
    SW_SHOW,
    WM_CLOSE,
    user32,
)
from ..winapi.screen import force_foreground
from ..winapi.terminals import is_terminal_window, list_terminal_windows

LAUNCH_TIMEOUT = 12.0
ERROR_LINGER = 4.0
HISTORY_LIMIT = 8


class TerminalSession:
    """记住水母打开过的终端窗口，并负责它们的显示 / 隐藏 / 重启。

    notify 在启动流程结束（成功或失败）时调用，用于唤醒 UI 线程重绘；
    save_history 在历史列表变化时调用，由调用方负责持久化。
    """

    def __init__(
        self,
        saved_history: list,
        notify: Callable[[], None],
        save_history: Callable[[list[int]], None],
    ) -> None:
        self.hwnd = 0
        self.history: list[int] = []
        self.launching = False
        self.error_until = 0.0
        self._notify = notify
        self._save_history = save_history

        for item in saved_history:
            try:
                h = int(item)
            except (TypeError, ValueError):
                continue
            if h not in self.history and is_terminal_window(h):
                self.history.append(h)
        self.hwnd = self.history[0] if self.history else 0

    # ---------------- 状态 ----------------
    def state(self) -> str:
        if self.launching:
            return "launching"
        if time.monotonic() < self.error_until:
            return "error"
        h = self.hwnd
        if h and user32.IsWindow(h):
            if user32.IsWindowVisible(h) and not user32.IsIconic(h):
                return "visible"
            return "hidden"
        return "none"

    def poll(self) -> None:
        """每帧检查：当前窗口是否还活着、是否需要接管、是否被最小化。"""
        h = self.hwnd
        if h and not user32.IsWindow(h):
            self.hwnd = 0
        if not self.hwnd:
            self.adopt()
            h = self.hwnd
        if h and user32.IsWindowVisible(h) and user32.IsIconic(h):
            user32.ShowWindow(h, SW_HIDE)
            log("auto-collapse on minimize")

    # ---------------- 历史 ----------------
    def _remember(self, hwnd: int) -> None:
        """把水母打开过的终端窗口记到最前面并持久化。"""
        if hwnd <= 0:
            return
        self.history = [hwnd] + [h for h in self.history if h != hwnd]
        del self.history[HISTORY_LIMIT:]
        self._save_history(list(self.history))

    def adopt(self) -> bool:
        """当前终端窗口已经关闭时，接管最近打开且仍然存在的那个。"""
        before = self.hwnd
        live = [h for h in self.history if is_terminal_window(h)]
        if live != self.history:
            self.history = live
            self._save_history(list(live))
        if not self.history:
            return False
        self.hwnd = self.history[0]
        if self.hwnd != before:
            log(f"adopt terminal hwnd={self.hwnd}")
        return True

    # ---------------- 显示 / 隐藏 ----------------
    def toggle(self, provider: str, provider_cfg: dict) -> None:
        if self.launching:
            return
        h = self.hwnd
        if not (h and user32.IsWindow(h)):
            self.hwnd = 0
            if not self.adopt():
                self.launch(provider, provider_cfg)
                return
            h = self.hwnd
        if user32.IsWindowVisible(h) and not user32.IsIconic(h):
            user32.ShowWindow(h, SW_HIDE)
            log("terminal hidden")
        else:
            self.show()

    def show(self) -> None:
        h = self.hwnd
        if not h or not user32.IsWindow(h):
            return
        if user32.IsIconic(h):
            user32.ShowWindow(h, SW_RESTORE)
        else:
            user32.ShowWindow(h, SW_SHOW)
        force_foreground(h)
        log("terminal shown")

    # ---------------- 启动 / 重启 ----------------
    def launch(
        self,
        provider: str,
        provider_cfg: dict,
        continue_last: bool = False,
    ) -> None:
        if self.launching:
            return
        self.launching = True
        self.error_until = 0.0
        threading.Thread(
            target=self._launch_worker,
            args=(provider, provider_cfg, continue_last),
            daemon=True,
        ).start()

    def restart(self, provider: str, provider_cfg: dict) -> None:
        h = self.hwnd
        if h and user32.IsWindow(h):
            user32.PostMessageW(h, WM_CLOSE, 0, 0)
        self.hwnd = 0
        self.launching = False
        self.launch(provider, provider_cfg)

    def _launch_worker(
        self, provider: str, provider_cfg: dict, continue_last: bool
    ) -> None:
        try:
            before = {h for h, _ in list_terminal_windows()}
            script = write_launch_script(provider, provider_cfg, continue_last)
            args = [
                WT, "-w", "new", "--title", TERM_TITLE,
                "cmd.exe", "/d", "/k", str(script),
            ]
            log("launch: " + " ".join(f'"{a}"' if " " in a else a for a in args))
            log(f"launch provider={provider}")
            subprocess.Popen(
                args,
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            found = 0
            deadline = time.time() + LAUNCH_TIMEOUT
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
                self.hwnd = found
                self._remember(found)
                log(f"terminal found hwnd={found}")
                self._notify()
            else:
                log("terminal window not found")
                self.error_until = time.monotonic() + ERROR_LINGER
        except Exception:
            log("launch failed\n" + traceback.format_exc())
            self.error_until = time.monotonic() + ERROR_LINGER
        finally:
            self.launching = False
            try:
                self._notify()
            except Exception:
                pass
