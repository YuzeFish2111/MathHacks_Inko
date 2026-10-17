"""Text recognition with EasyOCR: what a computer reads in the handwriting, and how confidently.

POST /api/analyze calls read_handwriting() and returns its text as recognizedText, for display only:
OCR never affects the score (OCR confidence isn't calibrated, and models can guess a famous sentence
like the pangram even from messy writing). If EasyOCR isn't installed or its model can't load,
read_handwriting() returns None and recognizedText is null.

Run on its own from the backend/ folder:
    python -m app.accuracy_evaluation <image path>     (e.g. a photo in tests/sample-images/)
The first run downloads the EasyOCR model, so it needs internet access.
HEIC photos (iPhone) need:  pip install pillow-heif
"""
import logging
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NamedTuple, Optional

import cv2
import numpy as np

from .image_pipeline import load_image, to_grayscale, resize_to_width
from .scoring_config import OCR_ENABLED, OCR_LANGUAGES

logger = logging.getLogger(__name__)


# STEP 7A: Load the pretrained English OCR model.
# gpu=False runs the model on the CPU.
# Load this once and reuse it when processing multiple images.
def load_reader():
    import easyocr
    return easyocr.Reader(list(OCR_LANGUAGES), gpu=False)


# The server shares one model: loading it takes seconds (and downloads it on first use), so it is
# loaded on the first request and reused. A failed load is remembered so every request doesn't retry.
_reader = None
_readerLoadFailed = False
_readerLock = threading.Lock()    # one OCR at a time: the model isn't built for parallel calls


def get_reader():
    """The shared EasyOCR reader, or None if OCR is disabled or can't be loaded."""
    global _reader, _readerLoadFailed
    if not OCR_ENABLED or _readerLoadFailed:
        return None
    if _reader is None:
        try:
            _reader = load_reader()
        except Exception:    # not installed, no internet for the model download, certificate problems...
            logger.exception("EasyOCR could not be loaded; recognizedText will be null")
            _readerLoadFailed = True
            return None
    return _reader


@dataclass
class OcrResult:
    confidencePct: Optional[float]    # character-weighted confidence, 0-100; None if no text was found
    recognizedText: str               # what the model read, one detected region per line
    detections: list                  # raw (boundingBox, text, confidence 0-1) tuples, in image pixels


def read_handwriting(grayscaleImage: np.ndarray) -> Optional[OcrResult]:
    """Run OCR on the straightened page. None if OCR is unavailable (the API then skips the feature).

    Pass the same image the overlays refer to (rectifiedImage), so detection boxes line up with it.
    """
    with _readerLock:
        reader = get_reader()
        if reader is None:
            return None
        recognizedText, meanConfidence, _, detections = measure_handwriting_legibility(grayscaleImage, reader)
    confidencePct = None if meanConfidence is None else 100.0 * meanConfidence
    return OcrResult(confidencePct=confidencePct, recognizedText=recognizedText, detections=list(detections))


class OcrConfidenceResult(NamedTuple):
    """OCR confidence is 0-1; ocrScore is the same confidence scaled to 0-100."""

    recognizedText: str
    ocrConfidence: Optional[float]
    ocrScore: Optional[float]
    detections: list[Any]


def measure_handwriting_legibility(gray_image, reader) -> OcrConfidenceResult:
    """
    Recognize text and calculate a preliminary OCR legibility score.

    Returns:
        OcrResult with recognizedText, ocrConfidence (0-1), ocrScore (0-100),
        and raw detections. Both numeric fields are None when no text is found.
        Confidence does not measure accuracy against a known transcription.
    """

    # Accept a prepared grayscale page (pageImage in the API).
    # It retains stroke detail that thresholding and noise removal may discard.
    # detail=1 preserves confidence values.
    # paragraph=False keeps individual text regions and their confidence values.
    results = reader.readtext(
        gray_image,
        detail=1,
        paragraph=False
    )

    text_parts = []
    weighted_confidence_sum = 0.0
    total_characters = 0

    for bounding_box, text, confidence in results:
        text = text.strip()

        # Count non-space characters, including letters, digits, and punctuation.
        character_count = sum(
            not character.isspace() for character in text
        )

        # Ignore empty detections, but retain low-confidence text.
        # Removing low-confidence detections would inflate the score.
        if character_count == 0:
            continue

        confidence = float(np.clip(confidence, 0.0, 1.0))

        text_parts.append(text)
        weighted_confidence_sum += confidence * character_count
        total_characters += character_count

    # No detection does not prove the handwriting deserves a score of zero.
    # It could also indicate an unsuitable photo or OCR failure.
    if total_characters == 0:
        return OcrConfidenceResult("", None, None, results)

    # Longer text regions contribute more than shorter regions.
    mean_confidence = weighted_confidence_sum / total_characters

    # Preliminary mapping: f(c) = 100 * c.
    # This rescales OCR confidence; it is not calibrated to human ratings.
    legibility_score = 100.0 * mean_confidence

    # Join regions in the order returned by OCR.
    # Complex page layouts may need separate reading-order handling.
    recognized_text = "\n".join(text_parts)

    return OcrConfidenceResult(recognized_text, mean_confidence, legibility_score, results)


def load_photo(path):
    """originalImage from any format OpenCV reads, plus HEIC (iPhone) through pillow-heif."""
    if Path(path).suffix.lower() not in (".heic", ".heif"):
        return load_image(path)
    if not Path(path).exists():
        raise FileNotFoundError(f"Could not read image: {path}")
    try:
        from pillow_heif import register_heif_opener
    except ImportError:
        raise ImportError("HEIC photos need pillow-heif: run  pip install pillow-heif") from None
    from PIL import Image
    register_heif_opener()
    return cv2.cvtColor(np.array(Image.open(path).convert("RGB")), cv2.COLOR_RGB2BGR)


def main(path):
    # Same input as the teammate's Step 3: grayscale, resized to the pipeline's standard width
    gray = resize_to_width(to_grayscale(load_photo(path)))
    reader = load_reader()

    result = measure_handwriting_legibility(gray, reader)

    print("\nOCR-predicted text:")
    print(result.recognizedText if result.recognizedText else "[No text detected]")

    if result.ocrScore is None:
        print("OCR confidence score: unavailable - no text detected.")
    else:
        print(f"Weighted OCR confidence: {result.ocrConfidence:.3f}")
        print(f"OCR confidence score: {result.ocrScore:.1f}/100")
    return result.ocrScore


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python -m app.accuracy_evaluation <image path>")
    main(sys.argv[1])
