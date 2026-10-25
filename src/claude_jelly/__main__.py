"""`python -m claude_jelly` 与 `claude-jelly` 命令入口。"""
from __future__ import annotations

import traceback

from .app import APP_NAME, log, main
from .win32 import user32


def _run() -> None:
    try:
        main()
    except Exception:
        err = traceback.format_exc()
        log("fatal\n" + err)
        try:
            user32.MessageBoxW(None, err[-1500:], APP_NAME, 0x10)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    _run()
