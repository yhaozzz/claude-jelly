"""水母绘制：精灵图、状态灯、提示气泡与边缘躲藏参数。"""
from __future__ import annotations

import math
import traceback

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .core import APP_DIR, log

SS = 2  # 超采样倍数
BODY_W, BODY_H = 150.0, 172.0
BUBBLE_PAD = 96.0  # 气泡向左右飘出的空间（逻辑像素）
BASE_W, BASE_H = BODY_W + BUBBLE_PAD * 2.0, BODY_H
JELLY_CX = BODY_W / 2.0 + BUBBLE_PAD  # 水母中心在画布中的 x

_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _font(size: int) -> ImageFont.FreeTypeFont:
    size = max(8, int(size))
    if size not in _font_cache:
        try:
            _font_cache[size] = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", size)
        except Exception:
            try:
                _font_cache[size] = ImageFont.load_default(size)
            except Exception:
                _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


def vertical_gradient(w: int, h: int, top: tuple, bottom: tuple) -> Image.Image:
    t = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    c = (
        np.array(top, dtype=np.float32)[None, None, :] * (1.0 - t)
        + np.array(bottom, dtype=np.float32)[None, None, :] * t
    )
    c = np.repeat(c, w, axis=1).astype(np.uint8)
    return Image.fromarray(c, "RGBA")


def premultiplied_bgra(img: Image.Image) -> bytes:
    arr = np.asarray(img.convert("RGBA"), dtype=np.uint8)
    a = arr[:, :, 3].astype(np.uint16)
    out = np.empty_like(arr)
    out[:, :, 0] = (arr[:, :, 2].astype(np.uint16) * a // 255).astype(np.uint8)
    out[:, :, 1] = (arr[:, :, 1].astype(np.uint16) * a // 255).astype(np.uint8)
    out[:, :, 2] = (arr[:, :, 0].astype(np.uint16) * a // 255).astype(np.uint8)
    out[:, :, 3] = arr[:, :, 3]
    return out.tobytes()


# --------------------------------------------------------------------------
# 精灵图（官方 Claude Code 像素水母）
# --------------------------------------------------------------------------
SPRITE_PATH = APP_DIR / "assets" / "claude_sprite.png"
SPRITE_BASE_W = 132.0
SPRITE_CY = 82.0
# 精灵图里伞盖（脑袋）占的高度比例，224/280 处是触手开始的接缝
SPRITE_HEAD_FRAC = 224.0 / 280.0

# ---- 泡泡出泡点（相对 SPRITE_CY 的纵向偏移，逻辑像素）----
BUBBLE_EXIT_OFFSET = -14.0     # 正常：伞盖中上部侧面
BUBBLE_EXIT_OFFSET_LOW = 18.0  # 贴着屏幕上边缘：改到身体下半部，否则刚冒出来就被裁掉
BUBBLE_RISE = 64.0             # 泡泡上升高度

# ---- 边缘躲藏 ----
EDGE_SNAP_RADIUS = 56.0   # 松手时脑袋离边缘多近才会躲藏（逻辑像素）
EDGE_PEEK = 0.30          # 底边躲藏时露出的比例
EDGE_PEEK_SIDE = 0.375    # 左右边缘：约 1/3 的身体藏在屏幕外，露出 2/3
EDGE_PEEK_TOP = 0.20      # 顶边少藏一点，避免把眼睛切掉
REDOCK_DELAY = 0.5        # 鼠标离开后延迟多久重新躲回去（秒）

_sprite_src: Image.Image | None = None
_sprite_loaded = False
_sprite_scaled: dict[tuple[int, int], Image.Image] = {}


def _load_sprite() -> Image.Image | None:
    global _sprite_src, _sprite_loaded
    if not _sprite_loaded:
        _sprite_loaded = True
        try:
            if SPRITE_PATH.exists():
                _sprite_src = Image.open(SPRITE_PATH).convert("RGBA")
        except Exception:
            log("load sprite failed\n" + traceback.format_exc())
            _sprite_src = None
    return _sprite_src


def _scaled_sprite(tw: int, th: int) -> Image.Image | None:
    if _sprite_src is None:
        return None
    key = (tw, th)
    img = _sprite_scaled.get(key)
    if img is None:
        img = _sprite_src.resize((tw, th), Image.LANCZOS)
        _sprite_scaled[key] = img
    return img


BUBBLE_COUNT = 5


def _draw_bubbles(
    ov: Image.Image, k: float, t: float, direction: int, low: bool = False
) -> None:
    """终端窗口显示时从水母侧面吐泡泡，direction=-1 向左、+1 向右。

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
    x0 = cx + direction * (SPRITE_BASE_W * 0.62) * k
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
    hang_sway=True 时挂着晃触手（贴在上边缘、终端正在显示时的彩蛋）。
    """
    k = scale * SS
    W = max(1, int(round(BASE_W * scale)))
    H = max(1, int(round(BASE_H * scale)))
    w = max(1, int(round(BASE_W * k)))
    h = max(1, int(round(BASE_H * k)))

    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # 泡泡先画在底层：从伞盖后面淡入，再露出身体轮廓
    if state == "visible" and bubble_dir:
        ov = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        _draw_bubbles(ov, k, t, bubble_dir, bubble_low)
        img.alpha_composite(ov)

    bob = math.sin(t * 1.7) * 2.0
    bw = SPRITE_BASE_W * (1.045 if hover else 1.0)
    bh = bw * sprite.height / sprite.width
    tw = max(1, int(round(bw * k)))
    th = max(1, int(round(bh * k)))
    sp = _scaled_sprite(tw, th)
    if sp is not None:
        if body_hidden:
            cut = max(1, int(round(sp.height * SPRITE_HEAD_FRAC)))
            sp = sp.crop((0, 0, sp.width, cut))
        elif hang_sway:
            sp = _sway_tentacles(sp, t, k)
        cx = JELLY_CX * k
        cy = (SPRITE_CY + bob) * k
        img.alpha_composite(sp, (int(round(cx - tw / 2.0)), int(round(cy - th / 2.0))))

    # ---- 状态灯 ----
    # "visible"（终端窗口正显示）改用吐泡泡表示，避免贴边时指示灯被切出屏幕
    if state in ("launching", "error", "hidden"):
        if state == "launching":
            dot = (242, 173, 74, 255)
        elif state == "error":
            dot = (222, 92, 82, 255)
        else:
            dot = (96, 196, 142, 255)
        side = bubble_dir if bubble_dir else 1
        dot_x = (JELLY_CX + side * (SPRITE_BASE_W / 2.0 - 5.0)) * k
        dot_y = (SPRITE_CY - bh / 2.0 + 6.0) * k
        r1 = 3.6 * k
        r2 = 2.4 * k
        d.ellipse([dot_x - r1, dot_y - r1, dot_x + r1, dot_y + r1],
                  fill=(255, 255, 255, 210))
        d.ellipse([dot_x - r2, dot_y - r2, dot_x + r2, dot_y + r2], fill=dot)

    # ---- 提示气泡 ----
    tip_rect = None
    if tip_shown and tip_text:
        font = _font(int(round(12.5 * k)))
        bbox = d.textbbox((0, 0), tip_text, font=font)
        tw2 = bbox[2] - bbox[0]
        th2 = bbox[3] - bbox[1]
        pad_x = 10.0 * k
        pad_y = 6.0 * k
        bwd = tw2 + pad_x * 2
        bhd = th2 + pad_y * 2
        bx = JELLY_CX * k - bwd / 2.0
        bx = max(3.0 * k, min(bx, w - bwd - 3.0 * k))
        by = 136.0 * k
        if by + bhd > h:
            by = h - bhd - 3.0 * k
        d.rounded_rectangle(
            [bx, by, bx + bwd, by + bhd],
            radius=11.0 * k,
            fill=(30, 28, 27, 236),
        )
        d.text((bx + pad_x - bbox[0], by + pad_y - bbox[1]),
               tip_text, font=font, fill=(251, 249, 246, 255))
        tip_rect = (
            int(bx / SS), int(by / SS),
            int((bx + bwd) / SS), int((by + bhd) / SS),
        )

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
    sprite = _load_sprite()
    if sprite is not None:
        return draw_sprite_frame(
            sprite, scale, t, hover, tip_shown, tip_text, state, body_hidden,
            bubble_dir, bubble_low, hang_sway,
        )

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
    if state == "visible" and bubble_dir:
        bub = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        _draw_bubbles(bub, k, t, bubble_dir, bubble_low)
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
    # "visible"（终端窗口正显示）改用吐泡泡表示
    if state in ("launching", "error", "hidden"):
        side = bubble_dir if bubble_dir else 1
        dot_x, dot_y = cx + side * rx * 0.78, cy - ry * 0.72
        if state == "launching":
            dot = (242, 173, 74, 255)
        elif state == "error":
            dot = (222, 92, 82, 255)
        else:
            dot = (96, 196, 142, 255)
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
        font = _font(int(round(12.5 * k)))
        bbox = d.textbbox((0, 0), tip_text, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        pad_x = 10.0 * k
        pad_y = 6.0 * k
        bw = tw + pad_x * 2
        bh = th + pad_y * 2
        bx = JELLY_CX * k - bw / 2.0
        bx = max(3.0 * k, min(bx, w - bw - 3.0 * k))
        by = 136.0 * k
        if by + bh > h:
            by = h - bh - 3.0 * k
        d.rounded_rectangle(
            [bx, by, bx + bw, by + bh],
            radius=11.0 * k,
            fill=(30, 28, 27, 236),
        )
        d.text((bx + pad_x - bbox[0], by + pad_y - bbox[1]),
               tip_text, font=font, fill=(251, 249, 246, 255))
        tip_rect = (
            int(bx / SS), int(by / SS),
            int((bx + bw) / SS), int((by + bh) / SS),
        )

    img = img.resize((W, H), Image.BOX)
    return img, tip_rect



def head_rect(scale: float) -> tuple[float, float, float, float]:
    """脑袋（伞盖）在窗口坐标里的大致矩形。"""
    sprite = _load_sprite()
    if sprite is not None:
        tw = SPRITE_BASE_W * scale
        th = tw * sprite.height / sprite.width
        cx = JELLY_CX * scale
        cy = SPRITE_CY * scale
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
    sprite = _load_sprite()
    if sprite is not None:
        tw = SPRITE_BASE_W * scale
        th = tw * sprite.height / sprite.width
        cx = JELLY_CX * scale
        cy = SPRITE_CY * scale
        return (cx - tw / 2.0, cy - th / 2.0, cx + tw / 2.0, cy + th / 2.0)
    cx = JELLY_CX * scale
    cy = 88.0 * scale
    return (cx - 42.0 * scale, cy - 34.0 * scale, cx + 42.0 * scale, cy + 78.0 * scale)


def clear_sprite_cache() -> None:
    """缩放尺寸变化后清掉精灵图缓存。"""
    _sprite_scaled.clear()
