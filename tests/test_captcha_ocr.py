from pathlib import Path
from types import SimpleNamespace

from boya_kit import captcha_ocr
from boya_kit.captcha_ocr import (
    ocr_captcha_provider,
    recognize_captcha_bytes,
    recognize_captcha_file,
)


def test_recognize_captcha_cleans_non_alnum(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        captcha_ocr,
        "_ocr_engine",
        lambda: SimpleNamespace(classification=lambda _data: "aB 1-2"),
    )
    image = tmp_path / "captcha.png"
    image.write_bytes(b"fake-image")

    assert recognize_captcha_file(image) == "aB12"
    assert recognize_captcha_bytes(b"fake-image") == "aB12"
    assert ocr_captcha_provider(SimpleNamespace(image_path=image)) == "aB12"


def test_recognize_captcha_returns_none_when_engine_missing(monkeypatch) -> None:
    monkeypatch.setattr(captcha_ocr, "_ocr_engine", lambda: None)
    assert recognize_captcha_bytes(b"x") is None
