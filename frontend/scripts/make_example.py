"""Generate the built-in "Try an example" photo.

Run once (macOS, uses the Bradley Hand system font):
    .venv/bin/python scripts/make_example.py

Writes web/img/example.jpg, which the Decoder's "Try an example" button sends to the analysis
backend like any other photo. Replace it with a real photo any time.
"""
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONT = "/System/Library/Fonts/Supplemental/Bradley Hand Bold.ttf"
W, H = 1240, 1130
INK = (28, 28, 38)

LINES = [
    "Dear Sam,",
    "I'll meet you at 10:50",
    "in Room 6B. Bring the",
    "modern clock and 5 cold",
    "drinks. Thanks! Lily",
]

# (line, char index) -> special effect. Indexes count characters in the line string.
EFFECTS = {
    (1, 7): "big",       # the second "e" in "meet" is much taller than its neighbors
    (2, 13): "float",    # the "r" in "Bring" floats above the line
    (4, 3): "lean",      # the "n" in "drinks" leans the wrong way
}
# (line, char index) -> how much of the normal advance to use after that character.
CRAMPED = {(3, 4): 0.5, **{(4, i): 0.66 for i in range(8, 13)}}  # "rn" in modern, "Thanks"


def paper() -> Image.Image:
    rng = np.random.default_rng(7)
    yy, xx = np.mgrid[0:H, 0:W]
    light = 1.0 - 0.07 * (((xx - W * 0.42) / W) ** 2 + ((yy - H * 0.38) / H) ** 2) * 2.2
    base = np.stack([246 * light, 245 * light, 238 * light], axis=-1)
    base += rng.normal(0, 1.6, base.shape)
    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


def main() -> None:
    rng = random.Random(42)
    img = paper()
    font_size = 84
    base_ascent = ImageFont.truetype(FONT, font_size).getmetrics()[0]
    y = 140
    for li, line in enumerate(LINES):
        x = 120 + rng.randint(-6, 10)
        line_slant = rng.uniform(-6, -3)  # negative rotates clockwise = leans right
        for ci, ch in enumerate(line):
            if ch == " ":
                x += int(font_size * 0.32) + rng.randint(0, 10)
                continue
            effect = EFFECTS.get((li, ci))
            size = int(font_size * rng.uniform(0.93, 1.07) * (1.75 if effect == "big" else 1))
            font = ImageFont.truetype(FONT, size)
            ascent = font.getmetrics()[0]
            r = font.getbbox(ch)[2]
            tile = Image.new("L", (r + 40, int(size * 1.6)), 0)
            ImageDraw.Draw(tile).text((20, 10), ch, font=font, fill=255)
            angle = line_slant + rng.uniform(-2.5, 2.5)
            if effect == "lean":
                angle = 13
            w0, h0 = tile.size
            tile = tile.rotate(angle, resample=Image.BICUBIC, expand=True)
            tile = tile.filter(ImageFilter.GaussianBlur(0.6))
            shift = rng.randint(-4, 4) - (34 if effect == "float" else 0)
            # Keep every glyph on the same baseline: undo the bigger ascent and the
            # extra room that rotate(expand=True) adds around the tile.
            px = int(x - (tile.width - w0) / 2)
            py = int(y + shift - (ascent - base_ascent) - (tile.height - h0) / 2)
            ink = Image.new("RGB", tile.size, INK)
            img.paste(ink, (px, py), tile)
            advance = font.getlength(ch) * (1.02 + rng.uniform(-0.02, 0.06))
            x += advance * CRAMPED.get((li, ci), 1.0)
        y += 185 + rng.randint(-8, 8)

    out_img = ROOT / "web" / "img" / "example.jpg"
    img.save(out_img, "JPEG", quality=88)
    print("wrote", out_img, out_img.stat().st_size // 1024, "KB")


if __name__ == "__main__":
    main()
