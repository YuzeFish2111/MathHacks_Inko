"""Turn any upload (PNG, JPEG, HEIC, WebP) into an upright JPEG the analysis backend can use.

Phones send HEIC and rotate photos with an EXIF flag instead of rotating the pixels.
cv2.imdecode ignores that flag, so we decode with Pillow, apply the rotation, and only
then send a plain JPEG on to the analysis backend.
"""
import base64
import io
from dataclasses import dataclass

import cv2
import numpy as np
import pillow_heif
from PIL import Image, ImageOps

from . import config
from .errors import InkoError

pillow_heif.register_heif_opener()

_HEIF_BRANDS = (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1")


def sniff_format(data: bytes) -> str | None:
    """Identify the file from its first bytes. File names and browser MIME types lie."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brands = data[8:64]
        if brands[:4] in (b"avif", b"avis"):
            return "avif"
        if any(brand in brands for brand in _HEIF_BRANDS):
            return "heic"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def open_upload(data: bytes) -> Image.Image:
    """Validate and decode an upload into an upright RGB image (EXIF rotation applied)."""
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise InkoError("file_too_big")
    if sniff_format(data) is None:
        raise InkoError("wrong_file_type")
    try:
        img = Image.open(io.BytesIO(data))
        if img.format == "JPEG" and max(img.size) > config.MAX_MODEL_SIDE:
            # Decode big JPEGs at reduced size: much faster for 12+ MP phone photos.
            scale = config.MAX_MODEL_SIDE / max(img.size)
            img.draft("RGB", (int(img.width * scale), int(img.height * scale)))
        img.load()
    except Exception as exc:
        raise InkoError("wrong_file_type") from exc
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass  # a broken EXIF block should never block the upload
    return _to_rgb_on_white(img)


def _to_rgb_on_white(img: Image.Image) -> Image.Image:
    """Flatten transparency onto white (a transparent canvas export must not turn black)."""
    if img.mode in ("I;16", "I;16B", "I;16L", "I"):
        arr = np.asarray(img, dtype=np.float32)
        top = float(arr.max()) or 1.0
        img = Image.fromarray(np.clip(arr * (255.0 / top), 0, 255).astype(np.uint8))
    if img.mode == "P":
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.getchannel("A"))
        return background
    return img.convert("RGB")


def fit(img: Image.Image, max_side: int) -> Image.Image:
    """Shrink so the long side is at most max_side. Never enlarges."""
    if max(img.size) <= max_side:
        return img
    out = img.copy()
    out.thumbnail((max_side, max_side), Image.LANCZOS)
    return out


def jpeg_bytes(img: Image.Image, quality: int = 85) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue()


def data_url(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def data_url_bytes(url: str) -> bytes:
    """The bytes inside a base64 data URL (the backend's rectifiedImage)."""
    return base64.b64decode(url.split(",", 1)[1])


def thumbnail_jpeg(image_bytes: bytes) -> bytes:
    """Small copy of an image for the Progress list."""
    return jpeg_bytes(fit(_to_rgb_on_white(Image.open(io.BytesIO(image_bytes))), config.THUMB_SIDE), 78)


@dataclass
class PreparedImage:
    pil: Image.Image        # upright RGB, long side <= MAX_MODEL_SIDE
    gray: np.ndarray        # grayscale copy for the tilt check
    jpeg: bytes             # what is sent to the analysis backend

    @property
    def width(self) -> int:
        return self.pil.width

    @property
    def height(self) -> int:
        return self.pil.height


def prepare(data: bytes) -> PreparedImage:
    """HEIC to JPEG, EXIF rotation applied, at most MAX_MODEL_SIDE px. The analysis backend
    decodes with OpenCV, which ignores EXIF and can't open HEIC, so this must happen first."""
    img = fit(open_upload(data), config.MAX_MODEL_SIDE)
    gray = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2GRAY)
    return PreparedImage(pil=img, gray=gray, jpeg=jpeg_bytes(img, 92))


def avatar_jpeg(data: bytes, side: int = 256) -> bytes:
    """Center-crop an uploaded profile picture to a square JPEG (HEIC welcome)."""
    img = open_upload(data)
    img = ImageOps.fit(img, (side, side), Image.LANCZOS)
    return jpeg_bytes(img, 85)
