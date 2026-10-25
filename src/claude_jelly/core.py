"""应用常量、配置读写与系统级小工具。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

from .win32 import SPI_GETWORKAREA, WNDENUMPROC, kernel32, user32

APP_NAME = "Claude Jelly"
WINDOW_CLASS = "ClaudeJellyWindow"
WINDOW_TITLE = APP_NAME
TERM_TITLE = "Claude Jelly"

HOME = Path.home()
APP_DIR = Path(__file__).resolve().parent
LOCAL_DIR = Path(os.environ.get("LOCALAPPDATA", str(HOME))) / "ClaudeJelly"
CONFIG_PATH = LOCAL_DIR / "config.json"
LOG_PATH = LOCAL_DIR / "jelly.log"
STARTUP_LNK = (
    Path(os.environ.get("APPDATA", str(HOME)))
    / "Microsoft/Windows/Start Menu/Programs/Startup/Claude Jelly.lnk"
)

WT = shutil.which("wt") or str(
    HOME / "AppData/Local/Microsoft/WindowsApps/wt.exe"
)


def find_claude() -> str:
    p = HOME / ".local" / "bin" / "claude.exe"
    if p.exists():
        return str(p)
    w = shutil.which("claude")
    return w or "claude"


CLAUDE = find_claude()


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


def log(msg: str) -> None:
    try:
        LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > 200_000:
            LOG_PATH.unlink()
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n")
    except Exception:
        pass


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    try:
        LOCAL_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        log("save_config failed\n" + traceback.format_exc())




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


def is_terminal_window(hwnd: int) -> bool:
    """句柄是否仍然是一个 Windows Terminal 窗口。

    持久化的旧句柄可能在重启后被别的窗口复用，所以不能只信 IsWindow。
    """
    try:
        if not hwnd or not user32.IsWindow(hwnd):
            return False
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        return cls.value == "CASCADIA_HOSTING_WINDOW_CLASS"
    except Exception:
        return False


def list_terminal_windows() -> list[tuple[int, str]]:
    """枚举 Windows Terminal 的顶层窗口。"""
    out: list[tuple[int, str]] = []

    def _cb(hwnd, _lparam):
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, cls, 256)
        if cls.value == "CASCADIA_HOSTING_WINDOW_CLASS":
            title = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title, 512)
            out.append((int(hwnd), title.value))
        return True

    cb = WNDENUMPROC(_cb)
    user32.EnumWindows(cb, 0)
    return out


def shortcut_exists() -> bool:
    return STARTUP_LNK.exists()


def _app_launch_command() -> tuple[str, str, str]:
    """开机自启用的 (可执行文件, 参数, 工作目录)。"""
    exe = Path(sys.executable)
    if exe.name.lower().startswith("claude-jelly"):
        return str(exe), "", str(exe.parent)
    entry = Path(sys.prefix) / "Scripts" / "claude-jelly.exe"
    if entry.exists():
        return str(entry), "", str(entry.parent)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    return str(exe), "-m claude_jelly", str(Path(__file__).resolve().parent)


def _ps_quote(value: str) -> str:
    """PowerShell 单引号字符串转义。"""
    return value.replace("'", "''")


def set_autostart(enabled: bool) -> bool:
    try:
        if enabled:
            target, arguments, workdir = _app_launch_command()
            STARTUP_LNK.parent.mkdir(parents=True, exist_ok=True)
            ps = (
                "$ws = New-Object -ComObject WScript.Shell; "
                f"$s = $ws.CreateShortcut('{_ps_quote(str(STARTUP_LNK))}'); "
                f"$s.TargetPath = '{_ps_quote(target)}'; "
                f"$s.Arguments = '{_ps_quote(arguments)}'; "
                f"$s.WorkingDirectory = '{_ps_quote(workdir)}'; "
                "$s.WindowStyle = 7; $s.Save()"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                creationflags=subprocess.CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
            )
            return shortcut_exists()
        STARTUP_LNK.unlink(missing_ok=True)
        return True
    except Exception:
        log("set_autostart failed\n" + traceback.format_exc())
        return False
