"""开机自启：在启动文件夹创建 / 删除快捷方式。"""
from __future__ import annotations

import subprocess
import sys
import traceback
from pathlib import Path

from ..config import APP_DIR, STARTUP_LNK, log


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
    return str(exe), "-m claude_jelly", str(APP_DIR)


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
