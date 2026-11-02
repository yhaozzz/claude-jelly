"""系统文件对话框。"""
from __future__ import annotations

import ctypes
import ctypes.wintypes as wt

from .bindings import (
    OFN_EXPLORER,
    OFN_FILEMUSTEXIST,
    OFN_NOCHANGEDIR,
    OFN_PATHMUSTEXIST,
    OPENFILENAMEW,
    comdlg32,
)


def _wide_buffer(text: str, extra: int = 1) -> ctypes.Array:
    """带内嵌 NUL 的宽字符缓冲区（LPWSTR 赋值会在第一个 NUL 截断）。"""
    buf = ctypes.create_unicode_buffer(len(text) + extra)
    for i, ch in enumerate(text):
        buf[i] = ch
    return buf


def pick_image_file(
    owner: int = 0,
    title: str = "Choose image",
    initial_dir: str = "",
    image_label: str = "Image files",
    all_label: str = "All files",
) -> str:
    """弹出系统文件选择框，返回选中的图片路径；用户取消时返回空串。"""
    file_buf = ctypes.create_unicode_buffer(32768)
    filter_buf = _wide_buffer(
        f"{image_label}\0*.png;*.jpg;*.jpeg;*.gif;*.bmp;*.webp\0"
        f"{all_label}\0*.*\0"
    )
    ofn = OPENFILENAMEW()
    ofn.lStructSize = ctypes.sizeof(OPENFILENAMEW)
    ofn.hwndOwner = owner
    ofn.lpstrFilter = ctypes.cast(filter_buf, wt.LPCWSTR)
    ofn.lpstrFile = ctypes.cast(file_buf, wt.LPWSTR)
    ofn.nMaxFile = len(file_buf)
    ofn.lpstrInitialDir = initial_dir or None
    ofn.lpstrTitle = title
    ofn.lpstrDefExt = "png"
    ofn.Flags = (
        OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_EXPLORER | OFN_NOCHANGEDIR
    )
    if not comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
        return ""
    return file_buf.value
