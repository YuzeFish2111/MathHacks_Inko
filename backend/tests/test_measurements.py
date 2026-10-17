import cv2
import numpy as np

from app.image_pipeline import find_text_lines, find_components
from app.measurements import compute_feature_measurements, measure_stroke_widths_px, measure_slant_std_deg

SCALE_MM_PER_PX = 0.1    # so 40 px = 4.0 mm


def draw_letter_line(baselineOffsetsPx=(0,) * 8, strokePx=5):
    """One line of 8 identical hollow 'letters' (20 x 40 px), 10 px apart, then a word gap of 50 px
    and 4 more letters. baselineOffsetsPx shifts letters up/down to make an uneven baseline."""
    inkMask = np.zeros((200, 600), np.uint8)
    xPx = 30
    for letterIndex in range(12):
        if letterIndex == 8:
            xPx += 40                                          # word gap: 10 + 40 = 50 px
        offsetPx = baselineOffsetsPx[letterIndex % len(baselineOffsetsPx)]
        topPx = 80 + offsetPx
        # Pixel-exact hollow box (cv2.rectangle draws edges 2 px thicker than asked)
        inkMask[topPx:topPx + 40, xPx:xPx + 20] = 255
        inkMask[topPx + strokePx:topPx + 40 - strokePx, xPx + strokePx:xPx + 20 - strokePx] = 0
        xPx += 30
    return inkMask


def measure(inkMask, scaleMmPerPx=SCALE_MM_PER_PX):
    textLines = find_components(inkMask, find_text_lines(inkMask))
    return compute_feature_measurements(inkMask, textLines, scaleMmPerPx, scaleMmPerPx)


def test_returns_the_eight_image_measurements():
    assert list(measure(draw_letter_line())) == [
        "textSizeMm", "xHeightMm", "baselineVariationMm", "slantStdDeg", "strokeContrastRatio",
        "strokeWidthMedianMm", "relativeLetterSpacing", "letterSpacingCv"]


def test_identical_letters_measure_as_perfectly_consistent():
    m = measure(draw_letter_line())
    assert abs(m["textSizeMm"] - 4.0) < 1e-9                 # 40 px x 0.1 mm/px
    assert abs(m["xHeightMm"] - 4.0) < 1e-9
    assert m["baselineVariationMm"] == 0
    assert abs(m["slantStdDeg"]) < 1e-9
    assert abs(m["relativeLetterSpacing"] - 10 / 40) < 1e-9  # word gap (50 px) is excluded
    assert m["letterSpacingCv"] == 0


def test_uneven_baseline_is_detected():
    assert measure(draw_letter_line(baselineOffsetsPx=(0, 6, -6, 3)))["baselineVariationMm"] > 0.3


def test_stroke_width_matches_drawn_pen_width():
    for strokePx in (3, 5, 7):
        m = measure(draw_letter_line(strokePx=strokePx))
        assert abs(m["strokeWidthMedianMm"] - strokePx * SCALE_MM_PER_PX) <= 0.1   # within 1 px


def test_stroke_contrast_sees_thick_and_thin_strokes():
    inkMask = np.zeros((200, 400), np.uint8)
    for rowIndex, thicknessPx in enumerate((3, 9, 3, 9)):
        inkMask[20 + 40 * rowIndex:20 + 40 * rowIndex + thicknessPx, 20:380] = 255
    widthsPx = measure_stroke_widths_px(inkMask)
    assert 2.5 <= np.percentile(widthsPx, 90) / np.percentile(widthsPx, 10) <= 3.5   # about 9 / 3


def test_slant_varies_when_letters_lean_differently():
    inkMask = np.zeros((200, 600), np.uint8)
    for letterIndex, leanPx in enumerate((-12, 0, 12, -12, 0, 12)):
        xPx = 40 + 70 * letterIndex
        cv2.line(inkMask, (xPx, 140), (xPx + leanPx, 80), 255, 6)
    textLines = find_components(inkMask, find_text_lines(inkMask))
    assert measure_slant_std_deg(textLines) > 5


def test_unknown_scale_gives_null_mm_values_but_keeps_the_rest():
    m = measure(draw_letter_line(), scaleMmPerPx=None)
    assert m["textSizeMm"] is None and m["xHeightMm"] is None and m["strokeWidthMedianMm"] is None
    assert m["slantStdDeg"] is not None and m["relativeLetterSpacing"] is not None


def test_too_little_writing_gives_null_not_zero():
    inkMask = np.zeros((200, 200), np.uint8)
    inkMask[80:120, 50:70] = 255                              # a single letter
    inkMask[85:115, 55:65] = 0
    m = measure(inkMask)
    assert m["textSizeMm"] is None
    assert m["slantStdDeg"] is None
    assert m["letterSpacingCv"] is None


def test_empty_page_gives_all_null():
    assert all(value is None for value in measure(np.zeros((200, 200), np.uint8)).values())
