"""Make the web logo, wordmark, and PWA icons from the Canva exports in designs/.

    .venv/bin/python scripts/make_icons.py
"""
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
DESIGNS = ROOT / "designs"
IMG = ROOT / "web" / "img"
ICONS = ROOT / "web" / "icons"

CIRCLE_BLUE = np.array([186, 196, 206], np.float32)   # #bac4ce, the logo circle
BROWN = (150, 126, 118)                               # #967e76, the wordmark


def logo_mark(size: int = 1024) -> Image.Image:
    """The round feather logo on a transparent background, as a perfect circle."""
    src = np.asarray(Image.open(DESIGNS / "just logo.png").convert("RGB")).astype(np.float32)
    blue = np.linalg.norm(src - CIRCLE_BLUE, axis=2) < 28
    ys, xs = np.where(blue)
    crop = Image.fromarray(src.astype(np.uint8)).crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    crop = crop.resize((size, size), Image.LANCZOS)  # also fixes the slight oval in the export
    # Repaint the outer ring solid blue: the export's soft edge leaves a light halo.
    arr = np.asarray(crop).copy()
    yy, xx = np.ogrid[:size, :size]
    ring = np.hypot(xx - size / 2 + 0.5, yy - size / 2 + 0.5) > size * 0.46
    arr[ring] = CIRCLE_BLUE.astype(np.uint8)
    crop = Image.fromarray(arr)
    big = 4 * size
    yy, xx = np.ogrid[:big, :big]
    r = big / 2 - 4
    inside = ((xx - big / 2 + 0.5) ** 2 + (yy - big / 2 + 0.5) ** 2) <= r * r
    mask = Image.fromarray((inside * 255).astype(np.uint8)).resize((size, size), Image.LANCZOS)
    out = crop.convert("RGBA")
    out.putalpha(mask)
    return out


def wordmark() -> Image.Image:
    """The script "inko" as brown ink with a real alpha channel (used as a CSS mask so
    it can switch color in dark mode)."""
    src = Image.open(DESIGNS / "logo & name.png").convert("RGB")
    arr = np.asarray(src).astype(np.float32)
    lum = arr.mean(axis=2)
    brownish = np.linalg.norm(arr - np.array(BROWN, np.float32), axis=2) < 70
    brownish[:, : arr.shape[1] // 3] = False  # skip the circle on the left
    ys, xs = np.where(brownish)
    pad = 12
    box = (xs.min() - pad, ys.min() - pad, xs.max() + pad, ys.max() + pad)
    crop = lum[box[1]:box[3], box[0]:box[2]]
    paper, ink = float(np.percentile(crop, 95)), float(np.percentile(lum[brownish], 20))
    alpha = np.clip((paper - crop) / (paper - ink), 0, 1)
    rgba = np.zeros(crop.shape + (4,), np.uint8)
    rgba[..., 0], rgba[..., 1], rgba[..., 2] = BROWN
    rgba[..., 3] = (alpha * 255).astype(np.uint8)
    img = Image.fromarray(rgba, "RGBA")
    return img.resize((img.width // 2, img.height // 2), Image.LANCZOS)


def full_bleed(mark: Image.Image, size: int, logo_fraction: float) -> Image.Image:
    """Square icon filled with the logo blue (for maskable and Apple icons)."""
    bg = Image.new("RGBA", (size, size), tuple(int(c) for c in CIRCLE_BLUE) + (255,))
    inner = int(size * logo_fraction)
    logo = mark.resize((inner, inner), Image.LANCZOS)
    bg.alpha_composite(logo, ((size - inner) // 2, (size - inner) // 2))
    return bg.convert("RGB")


def main() -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    ICONS.mkdir(parents=True, exist_ok=True)
    mark = logo_mark()
    mark.resize((256, 256), Image.LANCZOS).save(IMG / "logo-mark.png", optimize=True)
    wordmark().save(IMG / "wordmark.png", optimize=True)

    for size in (192, 512):
        mark.resize((size, size), Image.LANCZOS).save(ICONS / f"icon-{size}.png", optimize=True)
        # Maskable: the circle sits inside the 80% safe zone, the corners are blue.
        full_bleed(mark, size, 1.0).save(ICONS / f"icon-maskable-{size}.png", optimize=True)
    full_bleed(mark, 180, 1.0).save(ICONS / "apple-touch-icon.png", optimize=True)
    for size in (32, 64):
        mark.resize((size, size), Image.LANCZOS).save(ICONS / f"favicon-{size}.png", optimize=True)
    print("icons written to", ICONS)


if __name__ == "__main__":
    main()
