"""悬浮形象（默认像素水母 / 自定义图片）的加载、缩放与缓存。"""
from __future__ import annotations

import traceback
from pathlib import Path

from PIL import Image

from ...config import APP_DIR, log
from .constants import BASE_H, BODY_H, BODY_W, SPRITE_BASE_W, SPRITE_CY

SPRITE_PATH = APP_DIR / "assets" / "claude_sprite.png"

_sprite_path: Path | None = None  # None 表示默认水母
_sprite_src: Image.Image | None = None
_sprite_loaded = False
_sprite_scaled: dict[tuple[int, int], Image.Image] = {}


def load_sprite() -> Image.Image | None:
    global _sprite_src, _sprite_loaded
    if not _sprite_loaded:
        _sprite_loaded = True
        path = _sprite_path or SPRITE_PATH
        try:
            if path.exists():
                with Image.open(path) as im:
                    img = im.convert("RGBA")
                # 自定义图片可能非常大，先缩到合理尺寸，避免每帧缩放太慢
                if max(img.size) > 1024:
                    img.thumbnail((1024, 1024), Image.LANCZOS)
                # 全透明的图片会让水母点不到，直接当作加载失败
                max_alpha = img.getchannel("A").getextrema()[1]
                if _sprite_path is not None and max_alpha < 80:
                    raise ValueError("sprite is fully transparent")
                _sprite_src = img
        except Exception:
            log("load sprite failed\n" + traceback.format_exc())
            _sprite_src = None
    return _sprite_src


def set_sprite_image(path: str | Path | None) -> bool:
    """切换悬浮形象：path=None 恢复默认水母，返回是否加载成功。"""
    global _sprite_path, _sprite_src, _sprite_loaded
    previous = _sprite_path
    _sprite_path = Path(path) if path else None
    _sprite_src = None
    _sprite_loaded = False
    _sprite_scaled.clear()
    if load_sprite() is not None:
        return True
    # 图片打不开：回滚到原来的形象
    _sprite_path = previous
    _sprite_src = None
    _sprite_loaded = False
    _sprite_scaled.clear()
    load_sprite()
    return False


def is_custom_sprite() -> bool:
    """当前是否使用自定义图片（而非默认像素水母）。"""
    return _sprite_path is not None


def sprite_center_y() -> float:
    """形象中心在画布中的纵向位置（逻辑像素）。"""
    return SPRITE_CY if _sprite_path is None else BASE_H / 2.0


def display_size(sprite: Image.Image, hover: bool) -> tuple[float, float]:
    """图片在画布上的显示宽高（逻辑像素）。

    默认水母沿用固定宽度；自定义图片等比缩放到水母身体框内。
    """
    grow = 1.045 if hover else 1.0
    ratio = sprite.width / sprite.height if sprite.height else 1.0
    if _sprite_path is None:
        bw = SPRITE_BASE_W * grow
        return bw, bw / ratio
    max_w, max_h = BODY_W * grow, BODY_H * grow
    if max_w / max_h > ratio:
        bh = max_h
        bw = bh * ratio
    else:
        bw = max_w
        bh = bw / ratio
    return bw, bh


def scaled_sprite(tw: int, th: int) -> Image.Image | None:
    if _sprite_src is None:
        return None
    key = (tw, th)
    img = _sprite_scaled.get(key)
    if img is None:
        img = _sprite_src.resize((tw, th), Image.LANCZOS)
        _sprite_scaled[key] = img
    return img


def clear_sprite_cache() -> None:
    """缩放尺寸变化后清掉精灵图缓存。"""
    _sprite_scaled.clear()
