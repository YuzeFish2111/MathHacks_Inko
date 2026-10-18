"""Optional Jev (TypeSafe System One) photo check on top of OpenCV: three yes/no (Noul)
questions about the whole photo, asked together: taken at an angle? any handwriting?
strong shadows?

Runs only when TYPESAFE_API_KEY is set. Any error, or an answer slower than the
timeout, is skipped, so the app never depends on the network for a demo.
"""
import asyncio
import io
import logging
import os

from PIL import Image as PILImage

from . import config
from .imaging import PreparedImage, fit

log = logging.getLogger("inko")

MODEL = os.environ.get("INKO_JEV_MODEL", "jev-latest")
TIMEOUT = float(os.environ.get("INKO_JEV_TIMEOUT", "6"))

# Thresholds for acting on Jev's answers. Tune them on real photos.
TILTED_AT = 0.8
SHADOWS_AT = 0.75
NO_HANDWRITING_BELOW = 0.05

_client = None


def enabled() -> bool:
    return bool(config.TYPESAFE_API_KEY)


def _get_client():
    global _client
    if _client is None:
        from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy
        _client = AsyncTypeSafeClient(
            api_key=config.TYPESAFE_API_KEY,
            model=MODEL,
            headers={"TypeSafe-Danger-Zone-Images": "true"},
            retry=RetryPolicy(max_retries=1, timeout=TIMEOUT),
        )
    return _client


def _jpeg(img: PILImage.Image) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=88)  # baseline JPEG, as the API prefers
    return buf.getvalue()


def _photo_for_jev(image: PreparedImage) -> bytes:
    """Within the API's 280 to 1568 px limits."""
    img = fit(image.pil, 1568)
    if min(img.size) < 280:
        canvas = PILImage.new("RGB", (max(280, img.width), max(280, img.height)), "white")
        canvas.paste(img, ((canvas.width - img.width) // 2, (canvas.height - img.height) // 2))
        img = canvas
    return _jpeg(img)


async def _ask(state, questions):
    return await asyncio.wait_for(_get_client().system_one(state, questions), timeout=TIMEOUT + 2)


async def photo_check(image: PreparedImage) -> dict | None:
    """Probabilities for tilted / has_handwriting / shadows, or None if skipped."""
    if not enabled():
        return None
    try:
        from typesafe_sdk import Image, Noul   # inside the try: a missing SDK is skipped, not a crash
        result = await _ask(
            ["A student took this photo of their handwriting on paper so an app can score how legible it is:",
             Image(_photo_for_jev(image))],
            {
                "tilted": Noul(instructions=(
                    "Was the photo taken at a noticeable angle instead of from directly above the page, "
                    "so the sheet looks like a trapezoid and the writing looks stretched or squished in perspective? "
                    "A page that is only rotated on the table, but shot from straight above, does not count.")),
                "has_handwriting": Noul(instructions=(
                    "Does the photo show handwriting (letters, words, or numbers written by hand) that someone could try to read?")),
                "shadows": Noul(instructions=(
                    "Do strong shadows or very uneven lighting fall across the writing, making some letters hard to see?")),
            },
        )
        return {key: float(result.nouls[key].noul) for key in ("tilted", "has_handwriting", "shadows")}
    except Exception as exc:
        log.warning("Jev photo check skipped: %s", exc)
        return None
