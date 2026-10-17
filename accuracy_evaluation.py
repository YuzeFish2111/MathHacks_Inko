"""Preliminary OCR legibility score: how confidently EasyOCR can read the handwriting.

Run:  python accuracy_evaluation.py [image path]    (default: same image as preprocessing.py)
The first run downloads the EasyOCR model, so it needs internet access.
"""
import sys

import numpy as np

from preprocessing import DEFAULT_IMAGE_PATH, load_photo, preprocess


# STEP 7A: Load the pretrained English OCR model.
# gpu=False runs the model on the CPU.
# Load this once and reuse it when processing multiple images.
def load_reader():
    import easyocr
    return easyocr.Reader(["en"], gpu=False)


def measure_handwriting_legibility(gray_image, reader):
    """
    Recognize text and calculate a preliminary OCR legibility score.

    Returns:
        recognized_text: Text predicted by OCR.
        mean_confidence: Character-count-weighted confidence, from 0 to 1.
        legibility_score: Preliminary score, from 0 to 100.
                         None means no usable text was detected.
        results: Original OCR detections for inspection.
    """

    # Use the resized grayscale image from Step 3.
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
        return "", None, None, results

    # Longer text regions contribute more than shorter regions.
    mean_confidence = weighted_confidence_sum / total_characters

    # Preliminary mapping: f(c) = 100 * c.
    # This rescales OCR confidence; it is not calibrated to human ratings.
    legibility_score = 100.0 * mean_confidence

    # Join regions in the order returned by OCR.
    # Complex page layouts may need separate reading-order handling.
    recognized_text = "\n".join(text_parts)

    return recognized_text, mean_confidence, legibility_score, results


def main(path):
    gray, _, _ = preprocess(load_photo(path))
    reader = load_reader()

    # Store the score for later use in your overall handwriting rating.
    (
        recognized_text,
        ocr_confidence,
        handwriting_accuracy_score,
        ocr_results
    ) = measure_handwriting_legibility(gray, reader)

    print("\nOCR-predicted text:")
    print(recognized_text if recognized_text else "[No text detected]")

    if handwriting_accuracy_score is None:
        print("Handwriting accuracy score: unavailable — no text detected.")
    else:
        print(f"Weighted OCR confidence: {ocr_confidence:.3f}")
        print(f"Handwriting accuracy score: {handwriting_accuracy_score:.1f}/100")
    return handwriting_accuracy_score


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IMAGE_PATH)
