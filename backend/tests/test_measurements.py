import cv2
import numpy as np

from app.image_pipeline import find_text_lines, find_components
from app.measurements import (compute_feature_measurements, measure_stroke_widths_px, measure_slant_std_deg,
                              measure_x_height_px, classify_height_groups)

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


def measure(inkMask, canvasHeightPx=None):
    textLines = find_components(inkMask, find_text_lines(inkMask))
    return compute_feature_measurements(inkMask, textLines, canvasHeightPx or inkMask.shape[0])


def test_returns_the_nine_measurements():
    assert list(measure(draw_letter_line())) == [
        "textHeightCanvasRatio", "xHeightAscenderRatio", "baselineVariationRatio",
        "slantStdDeg", "letterHeightCv", "strokeContrastRatio", "strokeWidthRatio",
        "relativeLetterSpacing", "letterSpacingCv"]


def test_identical_letters_measure_as_perfectly_consistent():
    m = measure(draw_letter_line())
    assert abs(m["textHeightCanvasRatio"] - 0.2) < 1e-9                 # 40 px / 200 px canvas height
    assert m["xHeightAscenderRatio"] is None                 # no tall letters to compare with
    assert m["letterHeightCv"] == 0
    assert m["baselineVariationRatio"] == 0
    assert abs(m["slantStdDeg"]) < 1e-9
    assert abs(m["relativeLetterSpacing"] - 10 / 40) < 1e-9  # word gap (50 px) is excluded
    assert m["letterSpacingCv"] == 0


def test_uneven_baseline_is_detected():
    assert measure(draw_letter_line(baselineOffsetsPx=(0, 6, -6, 3)))["baselineVariationRatio"] > 0.075


def test_stroke_width_matches_drawn_pen_width():
    for strokePx in (3, 5, 7):
        inkMask = draw_letter_line(strokePx=strokePx)
        m = measure(inkMask)
        xHeightPx = measure_x_height_px(inkMask, find_components(inkMask, find_text_lines(inkMask)))
        assert abs(m["strokeWidthRatio"] - strokePx / xHeightPx) <= 1 / xHeightPx   # within 1 px


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


def test_canvas_height_changes_only_canvas_ratio():
    mask = draw_letter_line()
    original = measure(mask)
    taller = measure(mask, canvasHeightPx=400)
    assert taller.pop("textHeightCanvasRatio") == original.pop("textHeightCanvasRatio") / 2
    assert taller == original


def test_too_little_writing_gives_null_not_zero():
    inkMask = np.zeros((200, 200), np.uint8)
    inkMask[80:120, 50:70] = 255                              # a single letter
    inkMask[85:115, 55:65] = 0
    m = measure(inkMask)
    assert m["textHeightCanvasRatio"] is None
    assert m["letterSpacingCv"] is None


def test_empty_page_gives_all_null():
    assert all(value is None for value in measure(np.zeros((200, 200), np.uint8)).values())


# ---------- height groups: letters are only compared with letters of the same height ----------

def draw_mixed_height_line(xHeightPx=30, ascenderPx=50, descenderTailPx=15, sunkenPx=0, xHeightJitterPx=()):
    """A line mixing x-height letters, ascenders and descenders, like real lowercase writing.

    Pattern (repeated): x, x, ascender, x, descender, x, ascender, x. Baseline at y = 140.
    sunkenPx moves the 2nd letter (an x-height letter) down as a whole, off the line.
    xHeightJitterPx: per-x-height-letter height changes, to make same-height letters uneven.
    """
    pattern = "xxaxdxax" * 2
    inkMask = np.zeros((240, 900), np.uint8)
    baselinePx, xPx, xIndex = 140, 30, 0
    for letterIndex, kind in enumerate(pattern):
        heightPx = {"x": xHeightPx, "a": ascenderPx, "d": xHeightPx}[kind]
        if kind == "x" and xHeightJitterPx:
            heightPx += xHeightJitterPx[xIndex % len(xHeightJitterPx)]
            xIndex += 1
        shiftPx = sunkenPx if letterIndex == 1 else 0
        topPx, bottomPx = baselinePx - heightPx + shiftPx, baselinePx + shiftPx
        inkMask[topPx:bottomPx, xPx:xPx + 20] = 255
        inkMask[topPx + 4:bottomPx - 4, xPx + 4:xPx + 16] = 0
        if kind == "d":
            inkMask[bottomPx:bottomPx + descenderTailPx, xPx + 16:xPx + 20] = 255     # tail below the line
        xPx += 32
    return inkMask


def groups_in_order(inkMask):
    textLines = find_components(inkMask, find_text_lines(inkMask))
    groups = classify_height_groups(textLines)
    return [groups[c.componentId] for line in textLines for c in line.components if c.kind == "letter"]


def test_letters_are_sorted_into_height_groups():
    expected = {"x": "xHeight", "a": "ascender", "d": "descender"}
    assert groups_in_order(draw_mixed_height_line()) == [expected[kind] for kind in "xxaxdxax" * 2]


def test_sunken_letter_is_not_mistaken_for_a_descender():
    # The 2nd letter drops 12 px as a whole: its top is low too, so it stays an x-height letter
    assert groups_in_order(draw_mixed_height_line(sunkenPx=12))[1] == "xHeight"


def test_mixed_heights_are_not_counted_as_inconsistency():
    m = measure(draw_mixed_height_line())
    assert m["letterHeightCv"] == 0                         # every group is perfectly even
    heights = [30, 30, 50, 30, 45, 30, 50, 30] * 2          # yet the raw heights vary a lot
    assert np.std(heights) / np.mean(heights) > 0.2


def test_uneven_letters_within_a_group_are_detected():
    m = measure(draw_mixed_height_line(xHeightJitterPx=(0, 6, -6, 3)))
    assert m["letterHeightCv"] > 0.1


def test_x_height_is_compared_with_ascenders():
    m = measure(draw_mixed_height_line(xHeightPx=30, ascenderPx=50))
    assert abs(m["xHeightAscenderRatio"] - 30 / 50) < 1e-9


def test_descenders_dont_count_as_baseline_variation():
    assert measure(draw_mixed_height_line(descenderTailPx=20))["baselineVariationRatio"] == 0


def test_sunken_letters_still_count_as_baseline_variation():
    # Sunken letters drop as a whole (tops too), so unlike descenders they ARE counted. (The spread is a
    # robust MAD, which stays 0 while more than half the letters sit exactly on the line; isolated
    # off-line letters show up as overlay marks instead.)
    # Shift letters 8 px down and 8 px up in equal numbers, so the fitted baseline itself stays put
    inkMask = draw_mixed_height_line()
    xHeightIndexes = [i for i, kind in enumerate("xxaxdxax" * 2) if kind == "x"]
    for position, letterIndex in enumerate(xHeightIndexes[:8]):
        xPx = 30 + 32 * letterIndex
        shiftPx = 8 if position % 2 == 0 else -8
        inkMask[:, xPx:xPx + 20] = np.roll(inkMask[:, xPx:xPx + 20].copy(), shiftPx, axis=0)
    assert groups_in_order(inkMask).count("descender") == 2           # only the two real descenders
    assert measure(inkMask)["baselineVariationRatio"] > 0
