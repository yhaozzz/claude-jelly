"""显示语言：当前语言与界面文案。"""
from __future__ import annotations

DEFAULT_LANGUAGE = "zh"
LANGUAGE_ORDER = ("zh", "en")
LANGUAGE_NAMES = {"zh": "中文", "en": "English"}

_STRINGS: dict[str, dict[str, str]] = {
    "zh": {
        "tip.hide": "收起窗口",
        "tip.launching": "正在启动…",
        "tip.error": "启动失败",
        "tip.open": "打开 Claude Code",
        "menu.hide": "收起 Claude Code",
        "menu.open": "打开 Claude Code",
        "menu.continue": "继续上次会话",
        "menu.restart": "重新开始会话",
        "menu.size": "大小",
        "menu.opacity": "透明度",
        "menu.float": "浮动频率",
        "menu.float.still": "静止",
        "menu.float.slow": "慢",
        "menu.float.normal": "正常",
        "menu.float.fast": "快",
        "menu.sprite": "悬浮图片",
        "menu.sprite.pick": "选择图片…",
        "menu.sprite.reset": "恢复默认水母",
        "menu.provider": "大模型接口",
        "menu.provider.edit": "接口配置…",
        "menu.config.open": "打开配置文件",
        "menu.settings": "设置",
        "menu.language": "语言",
        "menu.topmost": "始终置顶",
        "menu.autostart": "开机自启",
        "menu.tip": "显示文字提示",
        "menu.quit": "退出",
        "provider.default": "官方 Claude",
        "provider.deepseek": "DeepSeek",
        "provider.custom": "自定义…",
        "dialog.base_url": "接口地址",
        "dialog.model": "模型名称",
        "dialog.show_key": "显示 API Key",
        "dialog.required": "接口地址和模型名称不能为空。",
        "dialog.invalid_value": "配置值不能包含引号或换行。",
        "dialog.cancel": "取消",
        "dialog.save": "保存",
        "dialog.pick_sprite": "选择悬浮图片",
        "dialog.image_files": "图片文件",
        "dialog.all_files": "所有文件",
        "dialog.image_error": (
            "这个文件无法作为图片打开。\n"
            "支持 PNG / JPG / GIF / BMP / WebP。"
        ),
    },
    "en": {
        "tip.hide": "Hide window",
        "tip.launching": "Launching…",
        "tip.error": "Launch failed",
        "tip.open": "Open Claude Code",
        "menu.hide": "Hide Claude Code",
        "menu.open": "Open Claude Code",
        "menu.continue": "Continue last session",
        "menu.restart": "Restart session",
        "menu.size": "Size",
        "menu.opacity": "Opacity",
        "menu.float": "Float speed",
        "menu.float.still": "Still",
        "menu.float.slow": "Slow",
        "menu.float.normal": "Normal",
        "menu.float.fast": "Fast",
        "menu.sprite": "Sprite",
        "menu.sprite.pick": "Choose image…",
        "menu.sprite.reset": "Reset to default jelly",
        "menu.provider": "Model provider",
        "menu.provider.edit": "Provider settings…",
        "menu.config.open": "Open config file",
        "menu.settings": "Settings",
        "menu.language": "Language",
        "menu.topmost": "Always on top",
        "menu.autostart": "Start with Windows",
        "menu.tip": "Show tooltips",
        "menu.quit": "Quit",
        "provider.default": "Official Claude",
        "provider.deepseek": "DeepSeek",
        "provider.custom": "Custom…",
        "dialog.base_url": "Base URL",
        "dialog.model": "Model",
        "dialog.show_key": "Show API key",
        "dialog.required": "Base URL and model are required.",
        "dialog.invalid_value": "Values cannot contain quotes or line breaks.",
        "dialog.cancel": "Cancel",
        "dialog.save": "Save",
        "dialog.pick_sprite": "Choose sprite image",
        "dialog.image_files": "Image files",
        "dialog.all_files": "All files",
        "dialog.image_error": (
            "This file could not be opened as an image.\n"
            "Supported: PNG / JPG / GIF / BMP / WebP."
        ),
    },
}

_language = DEFAULT_LANGUAGE


def normalize_language(value: object) -> str:
    """把配置里的任意值收敛为受支持的语言代码。"""
    if isinstance(value, str) and value in _STRINGS:
        return value
    return DEFAULT_LANGUAGE


def set_language(value: object) -> None:
    global _language
    _language = normalize_language(value)


def get_language() -> str:
    return _language


def t(key: str, **values: object) -> str:
    """返回当前语言的文案；缺词时回退中文，再回退 key。"""
    text = _STRINGS.get(_language, {}).get(key)
    if text is None:
        text = _STRINGS[DEFAULT_LANGUAGE].get(key, key)
    return text.format(**values) if values else text
