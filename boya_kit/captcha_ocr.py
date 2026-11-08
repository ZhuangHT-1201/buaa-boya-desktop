from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_CAPTCHA_CLEAN = re.compile(r"[^0-9A-Za-z]")


@lru_cache(maxsize=1)
def _ocr_engine() -> Any | None:
    """Lazy-load ddddocr; common for Chinese university SSO captchas."""
    try:
        import ddddocr
    except Exception as exc:  # pragma: no cover - optional dependency
        logger.warning("ddddocr unavailable for captcha OCR: %s", exc)
        return None
    try:
        # show_ad=False avoids noisy startup banners in background workers.
        return ddddocr.DdddOcr(show_ad=False)
    except TypeError:
        return ddddocr.DdddOcr()
    except Exception as exc:  # pragma: no cover - runtime init failure
        logger.warning("ddddocr init failed: %s", exc)
        return None


def captcha_ocr_available() -> bool:
    return _ocr_engine() is not None


def recognize_captcha_bytes(image: bytes) -> str | None:
    engine = _ocr_engine()
    if engine is None or not image:
        return None
    try:
        raw = engine.classification(image)
    except Exception as exc:
        logger.warning("captcha OCR failed: %s", exc)
        return None
    text = _CAPTCHA_CLEAN.sub("", str(raw or "")).strip()
    return text or None


def recognize_captcha_file(path: Path | str) -> str | None:
    image_path = Path(path)
    try:
        data = image_path.read_bytes()
    except OSError as exc:
        logger.warning("unable to read captcha image %s: %s", image_path, exc)
        return None
    return recognize_captcha_bytes(data)


def ocr_captcha_provider(challenge: object) -> str:
    """Callable compatible with AuthClient / login_account captcha providers."""
    image_path = getattr(challenge, "image_path", None)
    if not image_path:
        raise RuntimeError("验证码挑战缺少图片路径")
    text = recognize_captcha_file(image_path)
    if not text:
        raise RuntimeError("图形验证码自动识别失败，请手动登录")
    return text
