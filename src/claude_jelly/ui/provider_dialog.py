"""大模型接口配置对话框（tkinter，仅在选择接口时创建）。"""
from __future__ import annotations

import traceback

from ..config import APP_NAME, log
from ..i18n import t
from ..services.providers import bat_value


def prompt_provider_config(
    provider: str, base_url: str, model: str, api_key: str
) -> dict[str, str] | None:
    """弹出配置窗口，返回 {base_url, model, api_key}；取消返回 None。"""
    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:
        log("tkinter unavailable\n" + traceback.format_exc())
        return None

    root = tk.Tk()
    root.title(f"{APP_NAME} - {t(f'provider.{provider}')}")
    root.resizable(False, False)
    root.attributes("-topmost", True)

    url_var = tk.StringVar(value=base_url)
    model_var = tk.StringVar(value=model)
    key_var = tk.StringVar(value=api_key)
    show_key = tk.BooleanVar(value=False)
    result: dict[str, str] | None = None

    for row, (text, var) in enumerate(
        (
            (t("dialog.base_url"), url_var),
            (t("dialog.model"), model_var),
        )
    ):
        pad = (12 if row == 0 else 6, 0)
        tk.Label(root, text=text).grid(
            row=row, column=0, sticky="w", padx=12, pady=pad
        )
        tk.Entry(root, textvariable=var, width=48).grid(
            row=row, column=1, padx=12, pady=pad
        )

    tk.Label(root, text="API Key").grid(
        row=2, column=0, sticky="w", padx=12, pady=6
    )
    key_entry = tk.Entry(root, textvariable=key_var, width=48, show="*")
    key_entry.grid(row=2, column=1, padx=12, pady=6)

    def toggle_key() -> None:
        key_entry.configure(show="" if show_key.get() else "*")

    tk.Checkbutton(
        root, text=t("dialog.show_key"), variable=show_key, command=toggle_key
    ).grid(row=3, column=1, sticky="w", padx=8)

    def on_ok() -> None:
        nonlocal result
        url = url_var.get().strip()
        mdl = model_var.get().strip()
        key = key_var.get().strip()
        if not url or not mdl:
            messagebox.showwarning(
                t("menu.settings"), t("dialog.required"), parent=root
            )
            return
        try:
            for value in (url, mdl, key):
                bat_value(value)
        except ValueError:
            messagebox.showwarning(
                t("menu.settings"), t("dialog.invalid_value"), parent=root
            )
            return
        result = {"base_url": url, "model": mdl, "api_key": key}
        root.destroy()

    buttons = tk.Frame(root)
    buttons.grid(row=4, column=0, columnspan=2, pady=12)
    tk.Button(buttons, text=t("dialog.cancel"), width=10, command=root.destroy).pack(
        side="right", padx=(8, 12)
    )
    tk.Button(buttons, text=t("dialog.save"), width=10, command=on_ok).pack(
        side="right"
    )

    root.bind("<Return>", lambda _e: on_ok())
    root.bind("<Escape>", lambda _e: root.destroy())
    root.update_idletasks()
    w, h = root.winfo_width(), root.winfo_height()
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"+{x}+{y}")
    root.lift()
    root.focus_force()
    root.mainloop()
    return result
