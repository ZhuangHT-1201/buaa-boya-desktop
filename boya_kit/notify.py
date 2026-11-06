from __future__ import annotations

import ctypes
import os
import threading

from .service import mask_username


def notify_auth_required(username: str) -> None:
    """Show one non-blocking Windows warning when background re-login needs a captcha."""
    if os.name != "nt":
        return

    def show() -> None:
        message = (
            f"博雅账号 {mask_username(username)} 的统一认证登录已失效，"
            "并且自动登录需要验证码。\n\n"
            "请打开“博雅自动助手” → “账号管理”，选择该账号并点击“重新登录”。"
        )
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                message,
                "博雅自动助手：需要重新登录",
                0x00010030,
            )
        except Exception:
            pass

    threading.Thread(target=show, daemon=True).start()
