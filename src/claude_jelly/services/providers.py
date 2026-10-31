"""Claude Code 大模型接口配置（官方 / DeepSeek / 自定义）。"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import CLAUDE, HOME, LOCAL_DIR, TERM_TITLE

PROVIDER_ORDER = ("default", "deepseek", "custom")
PROVIDER_LABELS = {
    "default": "官方 Claude",
    "deepseek": "DeepSeek",
    "custom": "自定义…",
}
PROVIDER_DEFAULTS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com/anthropic",
        "model": "deepseek-flash",
    },
}
PROVIDER_SETTINGS = LOCAL_DIR / "provider-settings.json"
LAUNCH_SCRIPT = LOCAL_DIR / "launch.cmd"


def read_claude_env() -> dict[str, str]:
    """读取用户 Claude Code settings.json 里的 env（只读，用于预填）。"""
    try:
        path = HOME / ".claude" / "settings.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        env = data.get("env") if isinstance(data, dict) else None
        if isinstance(env, dict):
            return {str(k): str(v) for k, v in env.items()}
    except Exception:
        pass
    return {}


def bat_value(value: str) -> str:
    """转义要写入 .cmd 的字符串（% 需要写成 %%）。"""
    if any(ch in value for ch in ('"', "\r", "\n")):
        raise ValueError("配置值不能包含引号或换行")
    return value.replace("%", "%%")



def provider_values(provider: str, stored: dict) -> tuple[str, str, str]:
    """返回某个接口的 (接口地址, 模型名称, API Key)。"""
    if provider == "default":
        return "", "", ""
    conf = stored.get(provider)
    if not isinstance(conf, dict):
        conf = {}
    defaults = PROVIDER_DEFAULTS.get(provider, {})
    return (
        str(conf.get("base_url") or defaults.get("base_url", "")),
        str(conf.get("model") or defaults.get("model", "")),
        str(conf.get("api_key") or ""),
    )


def provider_env(provider: str, stored: dict) -> dict[str, str]:
    """写进 --settings 的 env；空字符串表示取消该项（视为未设置）。"""
    env = {
        "ANTHROPIC_BASE_URL": "",
        "ANTHROPIC_AUTH_TOKEN": "",
        "ANTHROPIC_MODEL": "",
        "ANTHROPIC_SMALL_FAST_MODEL": "",
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": "",
        "ANTHROPIC_DEFAULT_SONNET_MODEL": "",
        "ANTHROPIC_DEFAULT_OPUS_MODEL": "",
        "ANTHROPIC_DEFAULT_FABLE_MODEL": "",
    }
    if provider == "default":
        return env
    base_url, model, api_key = provider_values(provider, stored)
    env.update({
        "ANTHROPIC_API_KEY": "",
        "CLAUDE_CODE_USE_BEDROCK": "",
        "CLAUDE_CODE_USE_VERTEX": "",
        "CLAUDE_CODE_USE_FOUNDRY": "",
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_AUTH_TOKEN": api_key,
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_SMALL_FAST_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "ANTHROPIC_DEFAULT_FABLE_MODEL": model,
    })
    return env


def write_provider_settings(provider: str, stored: dict) -> Path:
    """生成只对本次会话生效的 Claude Code settings 文件。

    用户 settings.json 里的 env 优先级高于进程环境变量，所以必须用
    `--settings` 这个命令行级别的配置来覆盖。
    """
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    data = {"env": provider_env(provider, stored)}
    PROVIDER_SETTINGS.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return PROVIDER_SETTINGS


def write_launch_script(
    provider: str, stored: dict, continue_last: bool
) -> Path:
    """生成启动脚本，用 --settings 指定本次会话的模型接口。"""
    settings_path = write_provider_settings(provider, stored)
    lines = ["@echo off", f"title {TERM_TITLE}"]
    command = (
        f'"{bat_value(CLAUDE)}" '
        f'--settings "{bat_value(str(settings_path))}"'
    )
    if continue_last:
        command += " --continue"
    lines.append(command)

    text = "\r\n".join(lines) + "\r\n"
    try:
        data = text.encode("mbcs")
    except UnicodeEncodeError:
        text = "chcp 65001 >nul\r\n" + text
        data = text.encode("utf-8")
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    LAUNCH_SCRIPT.write_bytes(data)
    return LAUNCH_SCRIPT
