"""边缘躲藏：吸附判定、躲藏位置与缓动步进（纯函数，方便测试）。"""
from __future__ import annotations

import math

HEAD_RECT = tuple[float, float, float, float]
Pos = tuple[int, int]

# ---- 边缘躲藏参数 ----
EDGE_SNAP_RADIUS = 56.0   # 松手时脑袋离边缘多近才会躲藏（逻辑像素）
EDGE_PEEK = 0.30          # 底边躲藏时露出的比例
EDGE_PEEK_SIDE = 0.375    # 左右边缘：约 1/3 的身体藏在屏幕外，露出 2/3
EDGE_PEEK_TOP = 0.20      # 顶边少藏一点，避免把眼睛切掉
REDOCK_DELAY = 0.5        # 鼠标离开后延迟多久重新躲回去（秒）
MOVE_TAU = 0.093          # 贴边 / 探出时的位移时间常数（秒）


def nearest_edge(
    pos: Pos,
    head: HEAD_RECT,
    rect,
    snap_px: float,
) -> str | None:
    """脑袋离哪条边最近；不在吸附半径内则返回 None。"""
    hx0, hy0, hx1, hy1 = head
    sx0 = pos[0] + hx0
    sy0 = pos[1] + hy0
    sx1 = pos[0] + hx1
    sy1 = pos[1] + hy1
    dists = {
        "left": sx0 - rect.left,
        "right": rect.right - sx1,
        "top": sy0 - rect.top,
        "bottom": rect.bottom - sy1,
    }
    edge = min(dists, key=dists.get)
    if dists[edge] > snap_px:
        return None
    return edge


def dock_pos(
    edge: str,
    pos: Pos,
    head: HEAD_RECT,
    rect,
    revealed: bool,
) -> Pos:
    """计算躲到某条边时的窗口位置（窗口坐标->屏幕）。"""
    hx0, hy0, hx1, hy1 = head
    head_w = hx1 - hx0
    head_h = hy1 - hy0
    x, y = pos
    if edge in ("left", "right"):
        peek = max(4.0, EDGE_PEEK_SIDE * head_w)
        y = max(rect.top - hy0, min(y, rect.bottom - hy1))
    else:
        frac = EDGE_PEEK_TOP if edge == "top" else EDGE_PEEK
        peek = max(4.0, frac * head_h)
        x = max(rect.left - hx0, min(x, rect.right - hx1))

    if edge == "bottom":
        y = rect.bottom + peek - hy1
        if revealed:
            x = max(rect.left - hx0, min(x, rect.right - hx1))
            y = rect.bottom - hy1
    elif edge == "top":
        y = rect.top - peek - hy0
        if revealed:
            x = max(rect.left - hx0, min(x, rect.right - hx1))
            y = rect.top - hy0
    elif edge == "left":
        x = rect.left - peek - hx0
        if revealed:
            y = max(rect.top - hy0, min(y, rect.bottom - hy1))
            x = rect.left - hx0
    else:  # right
        x = rect.right + peek - hx1
        if revealed:
            y = max(rect.top - hy0, min(y, rect.bottom - hy1))
            x = rect.right - hx1
    return int(round(x)), int(round(y))


def ease_towards(
    pos: Pos, target: Pos, dt: float, tau: float = MOVE_TAU
) -> tuple[Pos, bool]:
    """指数缓动走向目标，返回 (新位置, 是否到达)。"""
    tx, ty = target
    x, y = pos
    if abs(tx - x) <= 1 and abs(ty - y) <= 1:
        return (tx, ty), True
    f = 1.0 - math.exp(-dt / tau)
    # 每帧至少挪 1 像素：高帧率下步长变小，round 会把最后几像素的小数步抹成 0，
    # 窗口就永远差几个像素到不了目标，anim_target 也清不掉
    sx = int(round((tx - x) * f)) or (1 if tx > x else (-1 if tx < x else 0))
    sy = int(round((ty - y) * f)) or (1 if ty > y else (-1 if ty < y else 0))
    return (x + sx, y + sy), False
