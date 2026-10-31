"""绘制相关的尺寸与时间常量（逻辑像素 / 秒）。"""
from __future__ import annotations

SS = 2  # 超采样倍数
BODY_W, BODY_H = 150.0, 172.0
BUBBLE_PAD = 96.0  # 气泡向左右飘出的空间（逻辑像素）
BASE_W, BASE_H = BODY_W + BUBBLE_PAD * 2.0, BODY_H
JELLY_CX = BODY_W / 2.0 + BUBBLE_PAD  # 水母中心在画布中的 x

# 精灵图（官方 Claude Code 像素水母）
SPRITE_BASE_W = 132.0
SPRITE_CY = 82.0
# 精灵图里伞盖（脑袋）占的高度比例，224/280 处是触手开始的接缝
SPRITE_HEAD_FRAC = 224.0 / 280.0

# 终端窗口存在（显示中或已收起）都算 Claude Code 在运行，一律吐泡泡
RUNNING_STATES = ("visible", "hidden")

# ---- 泡泡出泡点（相对 SPRITE_CY 的纵向偏移，逻辑像素）----
BUBBLE_EXIT_OFFSET = -14.0     # 正常：伞盖中上部侧面
BUBBLE_EXIT_OFFSET_LOW = 18.0  # 贴着屏幕上边缘：改到身体下半部，否则刚冒出来就被裁掉
BUBBLE_RISE = 64.0             # 泡泡上升高度
BUBBLE_COUNT = 5
