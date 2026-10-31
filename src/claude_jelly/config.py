"""应用常量、路径、配置读写与日志。"""
from __future__ import annotations

import json
import os
import shutil
import time
import traceback
from pathlib import Path

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
