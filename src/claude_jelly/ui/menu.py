"""右键菜单：只负责构建与返回命令，不执行动作。"""
from __future__ import annotations

from dataclasses import dataclass

from ..i18n import LANGUAGE_NAMES, LANGUAGE_ORDER, t
from ..services.providers import PROVIDER_ORDER
from ..winapi.bindings import (
    MF_CHECKED,
    MF_GRAYED,
    MF_POPUP,
    MF_SEPARATOR,
    MF_STRING,
    TPM_NONOTIFY,
    TPM_RETURNCMD,
    TPM_RIGHTBUTTON,
    WM_NULL,
    user32,
)

SIZE_PRESETS = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.2)
OPACITY_PRESETS = (0.2, 0.3, 0.4, 0.5, 0.6, 0.8, 1.0)
FLOAT_PRESETS = (0.0, 0.5, 1.0, 2.0)
FLOAT_LABEL_KEYS = (
    "menu.float.still",
    "menu.float.slow",
    "menu.float.normal",
    "menu.float.fast",
)

CMD_TOGGLE = 100
CMD_CONTINUE = 101
CMD_RESTART = 102
CMD_TOPMOST = 103
CMD_AUTOSTART = 104
CMD_QUIT = 105
CMD_TIP = 106
CMD_SIZE = 200
CMD_OPACITY = 300
CMD_FLOAT = 400
CMD_PROVIDER = 500
CMD_EDIT_PROVIDER = 510
CMD_OPEN_CONFIG = 511
CMD_PICK_SPRITE = 600
CMD_RESET_SPRITE = 601
CMD_LANGUAGE = 700


@dataclass(frozen=True)
class MenuState:
    """构建菜单需要展示的所有当前状态。"""

    window_state: str
    size_factor: float
    idle_opacity: float
    float_speed: float
    provider: str
    sprite_path: str
    topmost: bool
    autostart: bool
    show_tip: bool
    language: str


def show_context_menu(hwnd: int, sx: int, sy: int, state: MenuState) -> int:
    """弹出右键菜单，返回选中的命令 ID（取消时为 0）。"""
    menu = user32.CreatePopupMenu()
    size_menu = user32.CreatePopupMenu()
    opacity_menu = user32.CreatePopupMenu()
    float_menu = user32.CreatePopupMenu()
    sprite_menu = user32.CreatePopupMenu()
    settings_menu = user32.CreatePopupMenu()
    provider_menu = user32.CreatePopupMenu()
    language_menu = user32.CreatePopupMenu()
    try:
        toggle_label = t(
            "menu.hide" if state.window_state == "visible" else "menu.open"
        )
        running = state.window_state in ("visible", "hidden")
        user32.AppendMenuW(menu, MF_STRING, CMD_TOGGLE, toggle_label)
        user32.AppendMenuW(
            menu,
            MF_STRING | (MF_GRAYED if running else 0),
            CMD_CONTINUE, t("menu.continue"),
        )
        user32.AppendMenuW(
            menu,
            MF_STRING | (0 if running else MF_GRAYED),
            CMD_RESTART, t("menu.restart"),
        )
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)

        for i, v in enumerate(SIZE_PRESETS):
            flags = MF_STRING
            if abs(state.size_factor - v) < 0.001:
                flags |= MF_CHECKED
            user32.AppendMenuW(
                size_menu, flags, CMD_SIZE + i, f"{int(round(v * 100))}%"
            )
        user32.AppendMenuW(menu, MF_POPUP, size_menu, t("menu.size"))

        for i, v in enumerate(OPACITY_PRESETS):
            flags = MF_STRING
            if abs(state.idle_opacity - v) < 0.001:
                flags |= MF_CHECKED
            user32.AppendMenuW(
                opacity_menu, flags, CMD_OPACITY + i,
                f"{int(round(v * 100))}%",
            )
        user32.AppendMenuW(menu, MF_POPUP, opacity_menu, t("menu.opacity"))

        for i, speed in enumerate(FLOAT_PRESETS):
            flags = MF_STRING
            if abs(state.float_speed - speed) < 0.001:
                flags |= MF_CHECKED
            user32.AppendMenuW(
                float_menu, flags, CMD_FLOAT + i, t(FLOAT_LABEL_KEYS[i])
            )
        user32.AppendMenuW(menu, MF_POPUP, float_menu, t("menu.float"))

        user32.AppendMenuW(
            sprite_menu, MF_STRING, CMD_PICK_SPRITE, t("menu.sprite.pick")
        )
        user32.AppendMenuW(
            sprite_menu,
            MF_STRING | (0 if state.sprite_path else MF_GRAYED),
            CMD_RESET_SPRITE, t("menu.sprite.reset"),
        )
        user32.AppendMenuW(menu, MF_POPUP, sprite_menu, t("menu.sprite"))

        for i, name in enumerate(PROVIDER_ORDER):
            flags = MF_STRING
            if state.provider == name:
                flags |= MF_CHECKED
            user32.AppendMenuW(
                provider_menu, flags, CMD_PROVIDER + i,
                t(f"provider.{name}"),
            )
        user32.AppendMenuW(
            settings_menu, MF_POPUP, provider_menu, t("menu.provider")
        )
        user32.AppendMenuW(settings_menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(
            settings_menu,
            MF_STRING | (MF_GRAYED if state.provider == "default" else 0),
            CMD_EDIT_PROVIDER, t("menu.provider.edit"),
        )
        user32.AppendMenuW(
            settings_menu, MF_STRING, CMD_OPEN_CONFIG, t("menu.config.open")
        )
        user32.AppendMenuW(menu, MF_POPUP, settings_menu, t("menu.settings"))

        for i, code in enumerate(LANGUAGE_ORDER):
            flags = MF_STRING
            if state.language == code:
                flags |= MF_CHECKED
            user32.AppendMenuW(
                language_menu, flags, CMD_LANGUAGE + i,
                LANGUAGE_NAMES[code],
            )
        user32.AppendMenuW(
            menu, MF_POPUP, language_menu, t("menu.language")
        )

        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(
            menu, MF_STRING | (MF_CHECKED if state.topmost else 0),
            CMD_TOPMOST, t("menu.topmost"),
        )
        user32.AppendMenuW(
            menu, MF_STRING | (MF_CHECKED if state.autostart else 0),
            CMD_AUTOSTART, t("menu.autostart"),
        )
        user32.AppendMenuW(
            menu, MF_STRING | (MF_CHECKED if state.show_tip else 0),
            CMD_TIP, t("menu.tip"),
        )
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, CMD_QUIT, t("menu.quit"))

        user32.SetForegroundWindow(hwnd)
        cmd = user32.TrackPopupMenu(
            menu,
            TPM_RETURNCMD | TPM_RIGHTBUTTON | TPM_NONOTIFY,
            sx, sy, 0, hwnd, None,
        )
        user32.PostMessageW(hwnd, WM_NULL, 0, 0)
    finally:
        user32.DestroyMenu(menu)
    return cmd
