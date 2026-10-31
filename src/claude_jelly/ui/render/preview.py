"""开发用预览图生成（`--preview` / `claude-jelly-preview`）。"""
from __future__ import annotations

from PIL import Image

from ...config import LOCAL_DIR
from .frame import draw_frame


def preview(args: list[str]) -> None:
    scale = 2.0
    if "--scale" in args:
        try:
            scale = float(args[args.index("--scale") + 1])
        except Exception:
            pass
    t = 1.37
    variants = [
        ("preview_light.png", False, False, "打开 Claude Code", "none", 0),
        ("preview_hover.png", True, True, "打开 Claude Code", "none", 0),
        ("preview_active.png", True, True, "收起窗口", "visible", -1),
        ("preview_bubbles.png", True, True, "收起窗口", "visible", 1),
    ]
    out_dir = LOCAL_DIR / "previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, hover, tip, text, state, bdir in variants:
        img, _ = draw_frame(scale, t, hover, tip, text, state, False, bdir)
        light = Image.new("RGBA", img.size, (238, 239, 242, 255))
        light.alpha_composite(img)
        light.convert("RGB").save(out_dir / name)
    img, _ = draw_frame(scale, t, True, True, "打开 Claude Code", "none")
    dark = Image.new("RGBA", img.size, (32, 32, 34, 255))
    dark.alpha_composite(img)
    dark.convert("RGB").save(out_dir / "preview_dark.png")
    img, _ = draw_frame(scale, t, False, False, "", "none", True)
    light = Image.new("RGBA", img.size, (238, 239, 242, 255))
    light.alpha_composite(img)
    light.convert("RGB").save(out_dir / "preview_hidden.png")
    print(f"previews written to {out_dir}")
