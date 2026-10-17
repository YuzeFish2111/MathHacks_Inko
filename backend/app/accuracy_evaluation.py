"""Preliminary OCR legibility score: how confidently EasyOCR can read the handwriting.

Not yet part of POST /api/analyze; returning OCR results needs a contract change.
OCR confidence is separate from the app's overall legibilityScore.

Run from the backend/ folder:
    python -m app.accuracy_evaluation [image path]     (default: data/image0(37).heic at the project root)
The first run downloads the EasyOCR model, so it needs internet access.
HEIC photos (iPhone) need:  pip install pillow-heif
"""
import sys
from pathlib import Path
from typing import Any, NamedTuple, Optional

import cv2
import numpy as np

from .image_pipeline import load_image, to_grayscale, resize_to_width

# Found from this file's location, so it works from any folder
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_IMAGE_PATH = str(PROJECT_ROOT / "data" / "image0(37).heic")


# STEP 7A: Load the pretrained English OCR model.
# gpu=False runs the model on the CPU.
# Load this once and reuse it when processing multiple images.
def load_reader():
    import easyocr
    return easyocr.Reader(["en"], gpu=False)


class OcrResult(NamedTuple):
    """OCR confidence is 0-1; ocrScore is the same confidence scaled to 0-100."""

    recognizedText: str
    ocrConfidence: Optional[float]
    ocrScore: Optional[float]
    detections: list[Any]


def measure_handwriting_legibility(gray_image, reader) -> OcrResult:
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
        return OcrResult("", None, None, results)

    # Longer text regions contribute more than shorter regions.
    mean_confidence = weighted_confidence_sum / total_characters

    # Preliminary mapping: f(c) = 100 * c.
    # This rescales OCR confidence; it is not calibrated to human ratings.
    legibility_score = 100.0 * mean_confidence

    # Join regions in the order returned by OCR.
    # Complex page layouts may need separate reading-order handling.
    recognized_text = "\n".join(text_parts)

    return OcrResult(recognized_text, mean_confidence, legibility_score, results)


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
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IMAGE_PATH)
