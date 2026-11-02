from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent.parent
ASSET_DIR = ROOT / "assets"


def main() -> None:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    size = 512
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        ratio = y / max(1, size - 1)
        color = (
            int(58 + 38 * ratio),
            int(100 - 12 * ratio),
            int(232 - 22 * ratio),
            255,
        )
        draw.line((0, y, size, y), fill=color)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (8, 8, size - 8, size - 8),
        radius=110,
        fill=255,
    )
    rounded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rounded.paste(image, mask=mask)

    font_path = Path(r"C:\Windows\Fonts\msyhbd.ttc")
    if font_path.exists():
        font = ImageFont.truetype(str(font_path), 250)
    else:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(rounded)
    draw.text(
        (size / 2, size / 2 - 10),
        "博",
        fill="white",
        font=font,
        anchor="mm",
        stroke_width=3,
        stroke_fill=(31, 72, 190, 255),
    )
    rounded.save(
        ASSET_DIR / "boya.ico",
        sizes=[
            (16, 16),
            (24, 24),
            (32, 32),
            (48, 48),
            (64, 64),
            (128, 128),
            (256, 256),
        ],
    )
    rounded.resize((256, 256)).save(ASSET_DIR / "boya.png")
    print(ASSET_DIR / "boya.ico")


if __name__ == "__main__":
    main()
