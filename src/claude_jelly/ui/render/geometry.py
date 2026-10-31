"""水母在窗口坐标里的命中与缩放矩形。"""
from __future__ import annotations

from .constants import JELLY_CX, SPRITE_HEAD_FRAC
from .sprite import display_size, load_sprite, sprite_center_y


def head_rect(scale: float) -> tuple[float, float, float, float]:
    """脑袋（伞盖）在窗口坐标里的大致矩形。"""
    sprite = load_sprite()
    if sprite is not None:
        bw, bh = display_size(sprite, False)
        tw, th = bw * scale, bh * scale
        cx = JELLY_CX * scale
        cy = sprite_center_y() * scale
        return (
            cx - tw / 2.0, cy - th / 2.0,
            cx + tw / 2.0, cy - th / 2.0 + th * SPRITE_HEAD_FRAC,
        )
    # 没有精灵图时的程序化水母：以伞盖为准
    cx = JELLY_CX * scale
    cy = 88.0 * scale
    return (cx - 36.0 * scale, cy - 30.0 * scale, cx + 36.0 * scale, cy + 6.0 * scale)


def body_rect(scale: float) -> tuple[float, float, float, float]:
    """水母身体（含触手）在窗口坐标里的矩形，用于鼠标命中判定。

    泡泡不在此范围内，所以不会挡住点击。
    """
    sprite = load_sprite()
    if sprite is not None:
        bw, bh = display_size(sprite, False)
        tw, th = bw * scale, bh * scale
        cx = JELLY_CX * scale
        cy = sprite_center_y() * scale
        return (cx - tw / 2.0, cy - th / 2.0, cx + tw / 2.0, cy + th / 2.0)
    cx = JELLY_CX * scale
    cy = 88.0 * scale
    return (cx - 42.0 * scale, cy - 34.0 * scale, cx + 42.0 * scale, cy + 78.0 * scale)
