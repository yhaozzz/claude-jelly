"""帧合成：把精灵图、泡泡、状态灯与提示气泡画到同一张 RGBA 画布。"""
from __future__ import annotations

import math

import numpy as np
from PIL import Image, ImageDraw

from .bubbles import draw_bubbles
from .constants import (
    BASE_H,
    BASE_W,
    JELLY_CX,
    RUNNING_STATES,
    SPRITE_CY,
    SPRITE_HEAD_FRAC,
    SS,
)
from .jelly import draw_procedural_frame
from .sprite import (
    display_size,
    is_custom_sprite,
    load_sprite,
    scaled_sprite,
    sprite_center_y,
)
from .util import draw_tooltip


def _sway_tentacles(sp: Image.Image, t: float, k: float) -> Image.Image:
    """让伞盖以下的触手像垂下来的面条一样轻轻摆动。

    逐行做水平偏移：越靠下摆幅越大、相位往下传，形成悬挂时的波动。
    只改触手那几十行，开销很小。
    """
    arr = np.array(sp)
    h = arr.shape[0]
    seam = int(round(h * SPRITE_HEAD_FRAC))
    if seam >= h - 1:
        return sp
    out = arr.copy()
    span = float(h - seam)
    for y in range(seam, h):
        depth = (y - seam) / span
        amp = (0.6 + 3.4 * depth) * k
        off = int(round(math.sin(t * 1.9 - depth * 2.4) * amp))
        if not off:
            continue
        row = arr[y]
        dst = np.zeros_like(row)
        if off > 0:
            dst[off:] = row[:-off]
        else:
            dst[:off] = row[-off:]
        out[y] = dst
    return Image.fromarray(out, "RGBA")


def draw_sprite_frame(
    sprite: Image.Image,
    scale: float,
    t: float,
    hover: bool,
    tip_shown: bool,
    tip_text: str,
    state: str,
    body_hidden: bool = False,
    bubble_dir: int = 0,
    bubble_low: bool = False,
    hang_sway: bool = False,
) -> tuple[Image.Image, tuple[int, int, int, int] | None]:
    """用精灵图绘制一帧。返回 (RGBA 图, tooltip 矩形)。

    body_hidden=True 时只画伞盖（脑袋），触手整段裁掉，
    用来做“躲在屏幕边缘只露脑袋”的效果。
    bubble_low=True 时泡泡从身体下半部出发（贴着屏幕上边缘时用）。
    hang_sway=True 时挂着晃触手（贴在上边缘、Claude Code 正在运行时的彩蛋）。
    """
    k = scale * SS
    W = max(1, int(round(BASE_W * scale)))
    H = max(1, int(round(BASE_H * scale)))
    w = max(1, int(round(BASE_W * k)))
    h = max(1, int(round(BASE_H * k)))

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    bw, bh = display_size(sprite, hover)

    # 泡泡先画在底层：从伞盖后面淡入，再露出身体轮廓
    if state in RUNNING_STATES and bubble_dir:
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw_bubbles(ov, k, t, bubble_dir, bubble_low, bw)
        img.alpha_composite(ov)

    bob = math.sin(t * 1.7) * 2.0
    tw = max(1, int(round(bw * k)))
    th = max(1, int(round(bh * k)))
    sp = scaled_sprite(tw, th)
    if sp is not None:
        if body_hidden:
            cut = max(1, int(round(sp.height * SPRITE_HEAD_FRAC)))
            sp = sp.crop((0, 0, sp.width, cut))
        elif hang_sway and not is_custom_sprite():
            # 触手晃动只对默认水母有意义，自定义图片保持原样
            sp = _sway_tentacles(sp, t, k)
        cx = JELLY_CX * k
        cy = (sprite_center_y() + bob) * k
        img.alpha_composite(sp, (int(round(cx - tw / 2.0)), int(round(cy - th / 2.0))))

    # ---- 状态灯 ----
    # 终端在运行（显示或收起）时改用吐泡泡表示，这里只保留启动中 / 启动失败
    if state in ("launching", "error"):
        dot = (242, 173, 74, 255) if state == "launching" else (222, 92, 82, 255)
        side = bubble_dir if bubble_dir else 1
        if is_custom_sprite():
            # 自定义图片是矩形照片，指示灯放到图片外侧，避免压在图上
            dot_x = (JELLY_CX + side * (bw / 2.0 + 4.0)) * k
            dot_y = max(8.0, sprite_center_y() - bh / 2.0 + 8.0) * k
        else:
            dot_x = (JELLY_CX + side * (bw / 2.0 - 5.0)) * k
            dot_y = (SPRITE_CY - bh / 2.0 + 6.0) * k
        r1 = 3.6 * k
        r2 = 2.4 * k
        d.ellipse([dot_x - r1, dot_y - r1, dot_x + r1, dot_y + r1],
                  fill=(255, 255, 255, 210))
        d.ellipse([dot_x - r2, dot_y - r2, dot_x + r2, dot_y + r2], fill=dot)

    # ---- 提示气泡 ----
    tip_rect = None
    if tip_shown and tip_text:
        tip_rect = draw_tooltip(d, w, h, k, tip_text)

    img = img.resize((W, H), Image.BOX)
    return img, tip_rect


def draw_frame(
    scale: float,
    t: float,
    hover: bool,
    tip_shown: bool,
    tip_text: str,
    state: str,
    body_hidden: bool = False,
    bubble_dir: int = 0,
    bubble_low: bool = False,
    hang_sway: bool = False,
) -> tuple[Image.Image, tuple[int, int, int, int] | None]:
    """绘制一帧水母。返回 (RGBA 图, tooltip 矩形)。"""
    sprite = load_sprite()
    if sprite is not None:
        return draw_sprite_frame(
            sprite, scale, t, hover, tip_shown, tip_text, state, body_hidden,
            bubble_dir, bubble_low, hang_sway,
        )
    return draw_procedural_frame(
        scale, t, hover, tip_shown, tip_text, state, body_hidden,
        bubble_dir, bubble_low,
    )
