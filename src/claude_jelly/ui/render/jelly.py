"""程序化水母兜底绘制（精灵图加载失败时使用）。"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw

from .bubbles import draw_bubbles
from .constants import BASE_H, BASE_W, JELLY_CX, RUNNING_STATES, SS
from .util import draw_tooltip, vertical_gradient


def draw_procedural_frame(
    scale: float,
    t: float,
    hover: bool,
    tip_shown: bool,
    tip_text: str,
    state: str,
    body_hidden: bool = False,
    bubble_dir: int = 0,
    bubble_low: bool = False,
) -> tuple[Image.Image, tuple[int, int, int, int] | None]:
    """没有精灵图时用几何图形画一只水母。返回 (RGBA 图, tooltip 矩形)。"""
    k = scale * SS
    W = max(1, int(round(BASE_W * scale)))
    H = max(1, int(round(BASE_H * scale)))
    w = max(1, int(round(BASE_W * k)))
    h = max(1, int(round(BASE_H * k)))

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)

    # 泡泡在下层，从身体后面淡入
    if state in RUNNING_STATES and bubble_dir:
        bub = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        draw_bubbles(bub, k, t, bubble_dir, bubble_low)
        img.alpha_composite(bub)

    def X(v: float) -> float:
        return v * k

    def pt(x: float, y: float) -> tuple[float, float]:
        return (X(x), X(y))

    def ribbon(points, w0: float, w1: float, color, dr=None) -> None:
        n = len(points)
        if n < 2:
            return
        left = []
        right = []
        for j, (x, y) in enumerate(points):
            u = j / (n - 1)
            half = (w0 * (1.0 - u) + w1 * u) / 2.0
            if j == 0:
                dx = points[1][0] - x
                dy = points[1][1] - y
            elif j == n - 1:
                dx = x - points[-2][0]
                dy = y - points[-2][1]
            else:
                dx = points[j + 1][0] - points[j - 1][0]
                dy = points[j + 1][1] - points[j - 1][1]
            ln = math.hypot(dx, dy) or 1.0
            nx, ny = -dy / ln, dx / ln
            left.append(pt(x + nx * half, y + ny * half))
            right.append(pt(x - nx * half, y - ny * half))
        (dr if dr is not None else d).polygon(left + right[::-1], fill=color)

    bob = math.sin(t * 1.7) * 2.0
    squash = 1.0 + 0.028 * math.sin(t * 2.3)
    if hover:
        squash *= 1.015
    cx = JELLY_CX
    cy = 88.0 + bob
    rx = 36.0
    ry = 30.0 * squash

    # ---- 触手（在伞盖后面） ----
    for i in range(6):
        x0 = cx + (i - 2.5) * 10.2
        phase = i * 0.95
        length = 32.0 + (i % 3) * 7.0
        points = []
        steps = 16
        for j in range(steps + 1):
            u = j / steps
            sway = 6.5 * math.sin(t * 2.0 + phase + u * 2.8) * u
            yy = cy + 1.0 + u * length + 1.5 * math.sin(t * 1.6 + phase + u * 2.2) * u
            points.append((x0 + sway, yy))
        ribbon(points, 0.0, 6.0, (224, 146, 124, 200))
        ribbon(points, 0.0, 2.8, (247, 200, 183, 145))

    # ---- 伞盖 ----
    amp = 5.0
    bell = []
    n = 100
    for i in range(n + 1):
        a = math.pi - math.pi * i / n
        bell.append((cx + rx * math.cos(a), cy - ry * math.sin(a)))
    for i in range(1, n):
        u = i / n
        bell.append((cx + rx * (1.0 - 2.0 * u),
                     cy + amp * (0.5 - 0.5 * math.cos(6.0 * math.pi * u))))

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).polygon([pt(x, y) for x, y in bell], fill=255)
    grad = vertical_gradient(w, h, (243, 168, 133, 255), (205, 98, 68, 255))
    grad.putalpha(mask)
    img.alpha_composite(grad)

    # 伞盖底缘
    rim = [(cx + rx * (1.0 - 2.0 * i / 40),
            cy + amp * (0.5 - 0.5 * math.cos(6.0 * math.pi * (i / 40))))
           for i in range(41)]
    od.line([pt(x, y) for x, y in rim], fill=(180, 80, 54, 230),
            width=max(1, int(round(1.5 * k))), joint="curve")

    # 口腕（伞盖下方中央的褶皱触须）
    for sx, ph in ((-6.0, 0.4), (6.0, 2.1)):
        points = []
        for j in range(14):
            u = j / 13
            x = cx + sx * (1.0 - 0.5 * u) + 3.0 * math.sin(t * 2.4 + ph + u * 4.0) * u
            y = cy + 2.0 + u * 25.0
            points.append((x, y))
        ribbon(points, 5.5, 1.5, (246, 178, 158, 150), dr=od)

    # 高光
    od.ellipse(
        [pt(cx - rx * 0.46, cy - ry * 0.78), pt(cx - rx * 0.14, cy - ry * 0.42)],
        fill=(255, 231, 218, 45),
    )
    od.ellipse(
        [pt(cx - rx * 0.40, cy - ry * 0.70), pt(cx - rx * 0.26, cy - ry * 0.58)],
        fill=(255, 245, 238, 105),
    )

    # ---- 表情 ----
    blink_phase = t % 4.6
    blink = blink_phase < 0.12
    eye_y = cy - ry * 0.20
    for ex in (cx - rx * 0.31, cx + rx * 0.31):
        if blink:
            d.line(
                [pt(ex - 2.8, eye_y), pt(ex + 2.8, eye_y)],
                fill=(62, 45, 39, 255),
                width=max(1, int(round(1.4 * k))),
            )
        else:
            d.ellipse(
                [pt(ex - 2.9, eye_y - 3.6), pt(ex + 2.9, eye_y + 3.6)],
                fill=(62, 45, 39, 255),
            )
            od.ellipse(
                [pt(ex - 1.5, eye_y - 2.1), pt(ex + 0.1, eye_y - 0.5)],
                fill=(255, 255, 255, 225),
            )

    # 腮红
    for bx in (cx - rx * 0.60, cx + rx * 0.60):
        od.ellipse(
            [pt(bx - 4.4, cy - 2.4), pt(bx + 4.4, cy + 1.6)],
            fill=(255, 148, 138, 85),
        )

    # 微笑
    od.arc(
        [pt(cx - 4.2, cy - 1.0), pt(cx + 4.2, cy + 5.2)],
        start=25, end=155,
        fill=(62, 45, 39, 235),
        width=max(1, int(round(1.5 * k))),
    )

    # ---- 状态灯 ----
    # 终端在运行时用吐泡泡表示，这里只保留启动中 / 启动失败
    if state in ("launching", "error"):
        side = bubble_dir if bubble_dir else 1
        dot_x, dot_y = cx + side * rx * 0.78, cy - ry * 0.72
        dot = (242, 173, 74, 255) if state == "launching" else (222, 92, 82, 255)
        od.ellipse(
            [pt(dot_x - 3.6, dot_y - 3.6), pt(dot_x + 3.6, dot_y + 3.6)],
            fill=(255, 255, 255, 210),
        )
        od.ellipse(
            [pt(dot_x - 2.4, dot_y - 2.4), pt(dot_x + 2.4, dot_y + 2.4)],
            fill=dot,
        )

    # 半透明元素统一合成，避免直接覆盖造成“透洞”
    img.alpha_composite(ov)
    d = ImageDraw.Draw(img)

    # 躲藏时只保留伞盖，触手以下全部透明
    if body_hidden:
        cut = int(round((cy + amp + 1.0) * k))
        d.rectangle([0, cut, w, h], fill=(0, 0, 0, 0))

    # ---- 提示气泡 ----
    tip_rect = None
    if tip_shown and tip_text:
        tip_rect = draw_tooltip(d, w, h, k, tip_text)

    img = img.resize((W, H), Image.BOX)
    return img, tip_rect
