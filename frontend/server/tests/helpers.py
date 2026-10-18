"""Synthetic test photos and a stand-in for the analysis backend."""
import base64
import copy
import io
import json

import cv2
import numpy as np
from PIL import Image

from server import analysis, config

WORDS = ["hello there", "quick brown fox", "jumps over it", "lazy dog naps"]
FIXTURES = config.PROJECT_ROOT / "shared" / "fixtures"


def handwriting(width: int = 1200, height: int = 900, background=(255, 255, 255)) -> np.ndarray:
    img = np.full((height, width, 3), background, np.uint8)
    scale = width / 900
    for i, text in enumerate(WORDS):
        y = int(height * (0.2 + 0.18 * i))
        cv2.putText(img, text, (int(60 * scale), y), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX,
                    2.0 * scale, (20, 20, 20), max(2, int(3 * scale)), cv2.LINE_AA)
    return img


def encode(bgr: np.ndarray, fmt: str, **kwargs) -> bytes:
    pil = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil.save(buf, fmt, **kwargs)
    return buf.getvalue()


def page_on_table(tilt: bool) -> np.ndarray:
    """A sheet of paper with writing lying on a dark table, shot straight or at an angle."""
    table = np.full((1000, 1400, 3), (70, 80, 95), np.uint8)
    page = handwriting(700, 900)
    src = np.float32([[0, 0], [700, 0], [700, 900], [0, 900]])
    if tilt:
        dst = np.float32([[470, 90], [930, 90], [1150, 900], [250, 900]])  # top is much narrower
    else:
        dst = np.float32([[350, 50], [1050, 50], [1050, 950], [350, 950]])
    matrix = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(page, matrix, (1400, 1000))
    mask = cv2.warpPerspective(np.full((900, 700), 255, np.uint8), matrix, (1400, 1000))
    table[mask > 0] = warped[mask > 0]
    return table


def fixture(name: str) -> dict:
    """A shared/fixtures example response, with a real 1200 x 1600 JPEG as rectifiedImage."""
    body = json.loads((FIXTURES / f"{name}.json").read_text())
    if body["rectifiedImage"]:
        page = encode(np.full((1600, 1200, 3), 250, np.uint8), "JPEG")
        body["rectifiedImage"] = "data:image/jpeg;base64," + base64.b64encode(page).decode("ascii")
    return body


class SentPhotos(list):
    """The JPEGs sent to the fake backend, plus the wholePageSizePx and drawing flag each was sent with."""
    def __init__(self):
        super().__init__()
        self.wholePageSizes: list = []
        self.drawingFlags: list = []


def fake_backend(monkeypatch, response: dict | None = None, error: Exception | None = None) -> SentPhotos:
    """Replace the HTTP call to the analysis backend. Returns the list of JPEGs it was sent."""
    sent = SentPhotos()

    async def analyze(jpeg: bytes, wholePageSizePx=None, drawing=False) -> dict:
        sent.append(jpeg)
        sent.wholePageSizes.append(wholePageSizePx)
        sent.drawingFlags.append(drawing)
        if error:
            raise error
        return analysis.validate(copy.deepcopy(response or fixture("complete-response")))

    monkeypatch.setattr(analysis, "analyze", analyze)
    return sent
