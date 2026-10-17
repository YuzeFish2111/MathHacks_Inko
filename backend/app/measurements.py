"""The ten featureMeasurements.

Everything is measured in rectifiedImage pixels and converted to mm only at the end.
Any measurement that cannot be estimated reliably is None (null), never 0.
Only components of kind "letter" are used for shape and size; "mark" (dots, punctuation)
and "cluster" (joined letters) would distort them.
"""
import math
from typing import Optional

import cv2
import numpy as np
from scipy import stats

from .image_pipeline import LetterComponent, TextLine
from .scoring_config import (MIN_COMPONENTS_FOR_STATS, MIN_GAPS_FOR_STATS, MIN_LETTERS_FOR_BASELINE,
                             X_HEIGHT_ROW_FRACTION, WORD_GAP_MIN_RATIO)

# Median absolute deviation (MAD) x 1.4826 equals the standard deviation for normally distributed data,
# but a few extreme values (descenders, stray marks) barely move it. 1.4826 = 1 / 0.6745, where 0.6745
# is the 75th percentile of the standard normal distribution.
MAD_TO_STD = 1.4826


# ---------- helpers ----------

def _letters(textLines: list[TextLine]) -> list[LetterComponent]:
    """All clean letter candidates across every line."""
    return [component for line in textLines for component in line.components if component.kind == "letter"]


def _cv(values: list[float], minCount: int = MIN_COMPONENTS_FOR_STATS) -> Optional[float]:
    """Coefficient of variation (std / mean). None if too few values or the mean is 0.

    A unitless measure of unevenness: 0 = all values identical, 0.38 = they typically differ from the
    average by 38%. Being unitless, it means the same at any writing size.
    """
    if len(values) < minCount:
        return None
    mean = float(np.mean(values))
    return None if mean == 0 else float(np.std(values) / mean)


def _to_mm(valuePx: Optional[float], scaleMmPerPx: Optional[float]) -> Optional[float]:
    """Convert pixels to mm; None if either the value or the scale is unknown."""
    if valuePx is None or scaleMmPerPx is None:
        return None
    return valuePx * scaleMmPerPx


# ---------- 1. size ----------

def measure_text_size_px(textLines: list[TextLine]) -> Optional[float]:
    """Median height of letter components."""
    heightsPx = [component.heightPx for component in _letters(textLines)]
    return float(np.median(heightsPx)) if len(heightsPx) >= MIN_COMPONENTS_FOR_STATS else None


def measure_x_height_px(inkMask: np.ndarray, textLines: list[TextLine]) -> Optional[float]:
    """Median over lines of the lowercase-body height.

    Within each line, the rows holding at least X_HEIGHT_ROW_FRACTION of the line's peak ink
    form the x-height band; ascenders and descenders are too thin to reach that level.
    """
    xHeightsPx = []
    for line in textLines:
        rowInkCounts = (inkMask[line.topPx:line.bottomPx + 1] > 0).sum(axis=1)
        if rowInkCounts.size and rowInkCounts.max() > 0:
            xHeightsPx.append(int((rowInkCounts >= X_HEIGHT_ROW_FRACTION * rowInkCounts.max()).sum()))
    if not xHeightsPx or len(_letters(textLines)) < MIN_COMPONENTS_FOR_STATS:
        return None
    return float(np.median(xHeightsPx))


# ---------- 2. baseline ----------

def _letter_bottoms_px(line: TextLine) -> tuple[np.ndarray, np.ndarray]:
    """(x centre, bottom y) of each letter in a line."""
    letters = [component for component in line.components if component.kind == "letter"]
    centersXPx = np.array([component.xPx + component.widthPx / 2 for component in letters])
    bottomsPx = np.array([component.yPx + component.heightPx for component in letters])
    return centersXPx, bottomsPx


def fit_baseline(line: TextLine) -> Optional[tuple[float, float]]:
    """(slope, intercept) of a Theil-Sen line through the letter bottoms: y = slope * x + intercept.

    Theil-Sen takes the median of the slopes between every pair of points, so a few outliers
    (descenders, a floating letter) can't tilt the line the way they would an ordinary least-squares fit.
    None if the line has too few letters.
    """
    centersXPx, bottomsPx = _letter_bottoms_px(line)
    if len(bottomsPx) < MIN_LETTERS_FOR_BASELINE:
        return None
    slope, intercept, _, _ = stats.theilslopes(bottomsPx, centersXPx)
    return float(slope), float(intercept)


def measure_baseline_variation_px(textLines: list[TextLine]) -> Optional[float]:
    """Spread of letter bottoms around each line's fitted baseline.

    The spread is a robust standard deviation (1.4826 x median absolute deviation), so
    descenders (g, j, p, q, y) do not dominate the result.
    """
    residualsPx = []
    for line in textLines:
        baseline = fit_baseline(line)
        if baseline is None:
            continue
        slope, intercept = baseline
        centersXPx, bottomsPx = _letter_bottoms_px(line)
        residualsPx.extend(bottomsPx - (slope * centersXPx + intercept))
    if len(residualsPx) < MIN_COMPONENTS_FOR_STATS:
        return None
    residualsPx = np.array(residualsPx)
    return float(MAD_TO_STD * np.median(np.abs(residualsPx - np.median(residualsPx))))


# ---------- 3. shape consistency (slant) ----------
# Width/height and solidity spreads were removed in contract 1.3: they mixed up letter identity
# (an l and an o naturally differ) with inconsistency, so even perfect writing scored badly.

def letter_slant_deg(component: LetterComponent) -> Optional[float]:
    """One letter's slant in degrees (0 = upright), or None for a shape with no height.

    From second-order (central) moments of the outline: mu02 measures how spread out the shape is
    vertically and mu11 how much x and y vary together. Their ratio is the slope of x against y,
    i.e. how far the letter shifts sideways per unit of height (a regression of x on y).
    Lopsided upright letters (h, r, b, d) read up to ~17 degrees, so compare slants, not absolute values.
    """
    moments = cv2.moments(component.contour)
    if moments["mu02"] <= 0:
        return None
    return math.degrees(math.atan(moments["mu11"] / moments["mu02"]))


def measure_slant_std_deg(textLines: list[TextLine]) -> Optional[float]:
    """Standard deviation of letter slant, in degrees."""
    slantsDeg = [slantDeg for slantDeg in map(letter_slant_deg, _letters(textLines)) if slantDeg is not None]
    return float(np.std(slantsDeg)) if len(slantsDeg) >= MIN_COMPONENTS_FOR_STATS else None


# ---------- 4. stroke ----------

def measure_stroke_widths_px(inkMask: np.ndarray) -> np.ndarray:
    """Stroke width at every point along the middle of each stroke.

    The distance transform gives each ink pixel its distance to the nearest paper pixel.
    Its local maxima run along stroke centres, where the stroke width is about 2 x distance - 1.
    """
    distancePx = cv2.distanceTransform((inkMask > 0).astype(np.uint8), cv2.DIST_L2, cv2.DIST_MASK_5)
    # Local-maximum trick: dilate replaces each value with the largest in its 3x3 neighbourhood, so a pixel
    # equal to its dilated value is a peak: the centre line ("ridge") of a stroke
    isRidge = (distancePx > 0) & (distancePx >= cv2.dilate(distancePx, np.ones((3, 3), np.uint8)))
    # A centre pixel d px from the paper on both sides spans d + d - 1 px (it is counted on both sides)
    return 2 * distancePx[isRidge] - 1


def measure_stroke_width_median_px(strokeWidthsPx: np.ndarray) -> Optional[float]:
    return float(np.median(strokeWidthsPx)) if strokeWidthsPx.size >= MIN_COMPONENTS_FOR_STATS else None


def measure_stroke_contrast_ratio(strokeWidthsPx: np.ndarray) -> Optional[float]:
    """90th / 10th percentile stroke width (1.0 = perfectly even strokes)."""
    if strokeWidthsPx.size < MIN_COMPONENTS_FOR_STATS:
        return None
    p10, p90 = np.percentile(strokeWidthsPx, [10, 90])
    return float(p90 / p10) if p10 > 0 else None


# ---------- 5. spacing ----------

def find_gaps(textLines: list[TextLine]) -> list[dict]:
    """Every horizontal gap between neighbouring components, classified as "letter" or "word".

    Marks are skipped (a dot sits above its letter, not beside it). Overlapping neighbours
    count as a gap of 0. In each line, a gap wider than WORD_GAP_MIN_RATIO x the line's
    median gap is a space between words. Each gap is a box spanning the line's height,
    in rectifiedImage pixels, ready for overlayData.gaps.
    """
    gaps = []
    for line in textLines:
        components = [component for component in line.components if component.kind != "mark"]
        gapsPx = [max(0, right.xPx - (left.xPx + left.widthPx))
                  for left, right in zip(components, components[1:])]
        if not gapsPx:
            continue
        medianGapPx = float(np.median(gapsPx))
        for left, gapPx in zip(components, gapsPx):
            isWordGap = medianGapPx > 0 and gapPx > WORD_GAP_MIN_RATIO * medianGapPx
            gaps.append({
                "lineId": line.lineId,
                "kind": "word" if isWordGap else "letter",
                "xPx": left.xPx + left.widthPx,
                "yPx": line.topPx,
                "widthPx": gapPx,
                "heightPx": line.bottomPx - line.topPx + 1,
            })
    return gaps


def find_letter_gaps_px(textLines: list[TextLine]) -> list[float]:
    """Widths of the within-word (letter) gaps."""
    return [gap["widthPx"] for gap in find_gaps(textLines) if gap["kind"] == "letter"]


def measure_relative_letter_spacing(letterGapsPx: list[float], xHeightPx: Optional[float]) -> Optional[float]:
    """Median letter gap / x-height (unitless). Pixels are square, so no mm scale is needed."""
    if len(letterGapsPx) < MIN_GAPS_FOR_STATS or not xHeightPx:
        return None
    return float(np.median(letterGapsPx) / xHeightPx)


def measure_letter_spacing_cv(letterGapsPx: list[float]) -> Optional[float]:
    return _cv(letterGapsPx, minCount=MIN_GAPS_FOR_STATS)


# ---------- all ten ----------

def compute_feature_measurements(inkMask: np.ndarray, textLines: list[TextLine],
                                 scaleMmPerPxX: Optional[float],
                                 scaleMmPerPxY: Optional[float]) -> dict[str, Optional[float]]:
    """Return the eight measurements computed from the image (OCR adds ocrConfidencePct).

    mm values are None when the scale is unknown; unitless values and degrees are still measured.
    """
    xHeightPx = measure_x_height_px(inkMask, textLines)
    strokeWidthsPx = measure_stroke_widths_px(inkMask)
    letterGapsPx = find_letter_gaps_px(textLines)
    scaleMmPerPxMean = (scaleMmPerPxX + scaleMmPerPxY) / 2 if scaleMmPerPxX and scaleMmPerPxY else None

    return {
        "textSizeMm":            _to_mm(measure_text_size_px(textLines), scaleMmPerPxY),
        "xHeightMm":             _to_mm(xHeightPx, scaleMmPerPxY),
        "baselineVariationMm":   _to_mm(measure_baseline_variation_px(textLines), scaleMmPerPxY),
        "slantStdDeg":           measure_slant_std_deg(textLines),
        "strokeContrastRatio":   measure_stroke_contrast_ratio(strokeWidthsPx),
        "strokeWidthMedianMm":   _to_mm(measure_stroke_width_median_px(strokeWidthsPx), scaleMmPerPxMean),
        "relativeLetterSpacing": measure_relative_letter_spacing(letterGapsPx, xHeightPx),
        "letterSpacingCv":       measure_letter_spacing_cv(letterGapsPx),
    }
