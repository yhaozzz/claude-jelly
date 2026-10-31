"""绘制公共工具：字体、渐变、预乘像素与提示气泡。"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .constants import JELLY_CX, SS

_font_cache: dict[int, ImageFont.FreeTypeFont] = {}


def _font(size: int) -> ImageFont.FreeTypeFont:
    size = max(8, int(size))
    if size not in _font_cache:
        try:
            _font_cache[size] = ImageFont.truetype(
                "C:/Windows/Fonts/msyh.ttc", size
            )
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
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    arr = np.asarray(img, dtype=np.uint8)
    a = arr[:, :, 3].astype(np.uint16)
    out = np.empty_like(arr)
    out[:, :, 0] = arr[:, :, 2] * a // 255
    out[:, :, 1] = arr[:, :, 1] * a // 255
    out[:, :, 2] = arr[:, :, 0] * a // 255
    out[:, :, 3] = arr[:, :, 3]
    return out.tobytes()


def draw_tooltip(
    d: ImageDraw.ImageDraw, w: int, h: int, k: float, text: str
) -> tuple[int, int, int, int] | None:
    """在画布底部画提示气泡，返回逻辑像素坐标下的矩形。"""
    if not text:
        return None
    font = _font(int(round(12.5 * k)))
    bbox = d.textbbox((0, 0), text, font=font)
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
    d.text(
        (bx + pad_x - bbox[0], by + pad_y - bbox[1]),
        text,
        font=font,
        fill=(251, 249, 246, 255),
    )
    return (
        int(bx / SS), int(by / SS),
        int((bx + bw) / SS), int((by + bh) / SS),
    )
