"""运行状态下的泡泡粒子。"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from .constants import (
    BUBBLE_COUNT,
    BUBBLE_EXIT_OFFSET,
    BUBBLE_EXIT_OFFSET_LOW,
    BUBBLE_RISE,
    JELLY_CX,
    SPRITE_BASE_W,
    SPRITE_CY,
)


def draw_bubbles(
    ov: Image.Image,
    k: float,
    t: float,
    direction: int,
    low: bool = False,
    body_w: float = SPRITE_BASE_W,
) -> None:
    """Claude Code 运行时从水母侧面吐泡泡（窗口显示或收起都一样），
    direction=-1 向左、+1 向右。

    粒子只由时间 t 决定（无状态），每帧之间连续。泡泡在水母外侧淡入，
    沿一条向上的轨迹飘走，和水母身体之间留有空隙。
    """
    if direction == 0:
        return
    od = ImageDraw.Draw(ov)
    cx = JELLY_CX * k
    # 从身体外侧起飘，和身体留出一段空隙，稍微朝屏幕内侧偏，整体向上冒。
    # 贴着屏幕上边缘时改从身体下半部出发，泡泡才有地方升起来。
    exit_off = BUBBLE_EXIT_OFFSET_LOW if low else BUBBLE_EXIT_OFFSET
    cy = (SPRITE_CY + exit_off) * k
    # 从身体外缘再往外留 16 像素，自定义图片大小不同也不会压在身体上
    x0 = cx + direction * (body_w * 0.5 + 16.0) * k
    span = 20.0 * k
    rise = BUBBLE_RISE * k
    # 所有泡泡用同一个周期、相位均匀铺开：彼此始终等距，不会叠在一起
    life = 3.4
    for i in range(BUBBLE_COUNT):
        phase = i / BUBBLE_COUNT
        u = ((t / life) + phase) % 1.0
        wob = math.sin(t * 2.1 + i * 2.3) * 2.2 * u
        jitter_x = ((i * 53) % 19 - 9) * 0.55 * k
        jitter_y = ((i * 37) % 29 - 14) * 0.2 * k
        x = x0 + jitter_x + direction * span * u + wob
        y = cy + jitter_y - rise * u
        r = (2.3 + 4.2 * u) * k
        a = int(round(245 * math.sin(math.pi * u) ** 0.6))
        if a < 8:
            continue
        # 蓝色更明显：淡蓝填充 + 较深的蓝描边 + 高光
        od.ellipse([x - r, y - r, x + r, y + r],
                   fill=(132, 190, 246, int(a * 0.38)))
        od.ellipse(
            [x - r, y - r, x + r, y + r],
            outline=(52, 128, 232, a),
            width=max(1, int(round(1.0 * k))),
        )
        od.ellipse(
            [x - r * 0.54, y - r * 0.64, x + r * 0.02, y - r * 0.08],
            fill=(232, 245, 255, min(255, a + 20)),
        )
