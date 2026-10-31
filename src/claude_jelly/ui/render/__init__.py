"""水母绘制：精灵图、泡泡、程序化兜底与命中几何。"""
from __future__ import annotations

from .constants import (
    BASE_H,
    BASE_W,
    BUBBLE_EXIT_OFFSET,
    BUBBLE_PAD,
    BUBBLE_RISE,
    RUNNING_STATES,
    SPRITE_CY,
)
from .frame import draw_frame
from .geometry import body_rect, head_rect
from .sprite import clear_sprite_cache, is_custom_sprite, set_sprite_image
from .util import premultiplied_bgra

__all__ = [
    "BASE_H",
    "BASE_W",
    "BUBBLE_EXIT_OFFSET",
    "BUBBLE_PAD",
    "BUBBLE_RISE",
    "RUNNING_STATES",
    "SPRITE_CY",
    "body_rect",
    "clear_sprite_cache",
    "draw_frame",
    "head_rect",
    "is_custom_sprite",
    "premultiplied_bgra",
    "set_sprite_image",
]
