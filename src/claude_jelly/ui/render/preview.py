"""开发用预览图生成（`--preview` / `claude-jelly-preview`）。"""
from __future__ import annotations

from PIL import Image

from ...config import LOCAL_DIR, load_config
from ...i18n import DEFAULT_LANGUAGE, set_language, t
from .frame import draw_frame


def preview(args: list[str]) -> None:
    set_language(load_config().get("language", DEFAULT_LANGUAGE))
    scale = 2.0
    if "--scale" in args:
        try:
            scale = float(args[args.index("--scale") + 1])
        except Exception:
            pass
    phase = 1.37
    variants = [
        ("preview_light.png", False, False, t("tip.open"), "none", 0),
        ("preview_hover.png", True, True, t("tip.open"), "none", 0),
        ("preview_active.png", True, True, t("tip.hide"), "visible", -1),
        ("preview_bubbles.png", True, True, t("tip.hide"), "visible", 1),
    ]
    out_dir = LOCAL_DIR / "previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, hover, tip, text, state, bdir in variants:
        img, _ = draw_frame(scale, phase, hover, tip, text, state, False, bdir)
        light = Image.new("RGBA", img.size, (238, 239, 242, 255))
        light.alpha_composite(img)
        light.convert("RGB").save(out_dir / name)
    img, _ = draw_frame(scale, phase, True, True, t("tip.open"), "none")
    dark = Image.new("RGBA", img.size, (32, 32, 34, 255))
    dark.alpha_composite(img)
    dark.convert("RGB").save(out_dir / "preview_dark.png")
    img, _ = draw_frame(scale, phase, False, False, "", "none", True)
    light = Image.new("RGBA", img.size, (238, 239, 242, 255))
    light.alpha_composite(img)
    light.convert("RGB").save(out_dir / "preview_hidden.png")
    print(f"previews written to {out_dir}")
