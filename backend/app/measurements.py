"""The nine featureMeasurements.

Measurements use pixel ratios and degrees; physical dimensions are warning-only.
Height comparisons only compare letters within the same height group (x-height letters, ascenders,
descenders): see classify_height_groups.
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
                             X_HEIGHT_ROW_FRACTION, WORD_GAP_MIN_RATIO, X_HEIGHT_GROUP_MAX_RATIO,
                             ASCENDER_MIN_RATIO, DESCENDER_MIN_RATIO, DESCENDER_TOP_MIN_RATIO,
                             MIN_HEIGHT_GROUP_SIZE, HEIGHT_GROUP_BREAK_RATIO, HEIGHT_GROUP_MIN_SHARE)

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


def _ratio(
    numerator: Optional[float],
    denominator: Optional[float],
) -> Optional[float]:
    """Divide two measurements; None if either is missing or the denominator is invalid."""
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return float(numerator / denominator)

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


def small_letter_cluster(letterHeightsPx: list[float]) -> tuple[float, Optional[float]]:
    """A line's small letters, found from the letters' own heights (top to bottom).

    Sort the heights and find the natural break between small letters and tall ones (capitals,
    b, d, h, k, l, and g, p, y with their tails): the biggest proportional jump between neighbours.
    It counts if it is at least HEIGHT_GROUP_BREAK_RATIO and the cluster below it holds at least
    HEIGHT_GROUP_MIN_SHARE of the letters (and 2). Own heights, not heights above the baseline, so a
    letter that has sunk or floated off the line still counts as small.

    Returns (bodyPx, smallMaxPx): the small letters' median height (the x-height reference) and the
    tallest small letter, or (median of all, None) when there is no clear break. Works however many
    tall letters a sentence has ("Blah blah blah" is mostly tall letters, which broke the old rule of
    taking the line's median letter as the small-letter height).
    """
    heights = sorted(h for h in letterHeightsPx if h > 0)
    if not heights:
        return 0.0, None
    minLower = max(2, int(np.ceil(HEIGHT_GROUP_MIN_SHARE * len(heights))))
    bestJump, bestSplit = 1.0, None
    for split in range(minLower, len(heights)):          # heights[:split] is the lower cluster
        jump = heights[split] / heights[split - 1]
        if jump > bestJump:
            bestJump, bestSplit = jump, split
    if bestSplit is not None and bestJump >= HEIGHT_GROUP_BREAK_RATIO:
        return float(np.median(heights[:bestSplit])), float(heights[bestSplit - 1])
    return float(np.median(heights)), None


def classify_height_groups(textLines: list[TextLine]) -> dict[str, str]:
    """componentId -> height group, for letters on lines with a fitted baseline.

    Groups: "xHeight" (a, e, o ...), "ascender" (b, d, h, k, l, capitals), "descender" (g, j, p, q, y),
    "ascenderDescender" (both, e.g. a looped f), or "intermediate" (unclear; never compared).

    Per line, small_letter_cluster splits the letters at the natural break in their own heights:
    - at or below the break, and not a descender -> "xHeight" (even if written a bit too tall, so
      that unevenness is still measured);
    - above the break -> "ascender" if its top rises at least ASCENDER_MIN_RATIO x the small-letter
      height above the baseline, otherwise "intermediate";
    - a tail more than DESCENDER_MIN_RATIO below the baseline with the top still level -> "descender"
      (a letter whose top AND bottom are low has sunk below the line, so it stays in its group).
    With no clear break (all letters about one height) the old rule applies: top at most
    X_HEIGHT_GROUP_MAX_RATIO x the median height -> "xHeight".
    """
    groups = {}
    for line in textLines:
        baseline = fit_baseline(line)
        if baseline is None:
            continue
        slope, intercept = baseline
        letters = [component for component in line.components if component.kind == "letter"]
        bodyPx, smallMaxPx = small_letter_cluster([letter.heightPx for letter in letters])
        if bodyPx <= 0:
            continue
        for letter in letters:
            baselineYPx = slope * (letter.xPx + letter.widthPx / 2) + intercept
            aboveRatio = (baselineYPx - letter.yPx) / bodyPx
            belowRatio = (letter.yPx + letter.heightPx - baselineYPx) / bodyPx
            isAscender = aboveRatio >= ASCENDER_MIN_RATIO
            isDescender = belowRatio > DESCENDER_MIN_RATIO and aboveRatio >= DESCENDER_TOP_MIN_RATIO
            isSmall = letter.heightPx <= smallMaxPx if smallMaxPx is not None else aboveRatio <= X_HEIGHT_GROUP_MAX_RATIO
            if isAscender and isDescender:
                groups[letter.componentId] = "ascenderDescender"
            elif isDescender:
                groups[letter.componentId] = "descender"
            elif isSmall:
                groups[letter.componentId] = "xHeight"
            elif isAscender:
                groups[letter.componentId] = "ascender"
            else:
                groups[letter.componentId] = "intermediate"
    return groups


def _heights_by_group(textLines: list[TextLine], heightGroups: dict[str, str]) -> dict[str, list[int]]:
    """Letter heights in px, collected per height group."""
    heightsPx: dict[str, list[int]] = {}
    for letter in _letters(textLines):
        group = heightGroups.get(letter.componentId)
        if group is not None:
            heightsPx.setdefault(group, []).append(letter.heightPx)
    return heightsPx


def measure_x_height_ascender_ratio(textLines: list[TextLine], heightGroups: dict[str, str]) -> Optional[float]:
    """Median x-height-letter height / median ascender height (the typographic x-height proportion).

    Compares one height group with another instead of mixing them. None unless both groups
    have at least MIN_HEIGHT_GROUP_SIZE letters.
    """
    heightsPx = _heights_by_group(textLines, heightGroups)
    xHeightsPx, ascenderHeightsPx = heightsPx.get("xHeight", []), heightsPx.get("ascender", [])
    if len(xHeightsPx) < MIN_HEIGHT_GROUP_SIZE or len(ascenderHeightsPx) < MIN_HEIGHT_GROUP_SIZE:
        return None
    return _ratio(float(np.median(xHeightsPx)), float(np.median(ascenderHeightsPx)))


def measure_letter_height_cv(textLines: list[TextLine], heightGroups: dict[str, str]) -> Optional[float]:
    """How much letters vary in height within their own height group (0 = every group perfectly even).

    Each letter's height is divided by its group's median height, so x-height letters are only compared
    with x-height letters and ascenders with ascenders; the normalised heights are pooled and their
    standard deviation returned (a coefficient of variation, since their median is 1). Descenders and
    in-between letters are left out: there are too few of them, and their shapes vary naturally.
    """
    normalisedHeights = []
    for group in ("xHeight", "ascender"):
        groupHeightsPx = _heights_by_group(textLines, heightGroups).get(group, [])
        if len(groupHeightsPx) >= MIN_HEIGHT_GROUP_SIZE:
            groupMedianPx = float(np.median(groupHeightsPx))
            normalisedHeights.extend(heightPx / groupMedianPx for heightPx in groupHeightsPx)
    if len(normalisedHeights) < MIN_COMPONENTS_FOR_STATS:
        return None
    return float(np.std(normalisedHeights))


def measure_baseline_variation_px(textLines: list[TextLine],
                                  heightGroups: Optional[dict[str, str]] = None) -> Optional[float]:
    """Spread of letter bottoms around each line's fitted baseline.

    Only letters that should sit on the baseline are compared: descenders (g, j, p, q, y) hang below it
    by design, so they are left out when heightGroups is given. The spread is a robust standard
    deviation (1.4826 x median absolute deviation), so a few odd letters don't dominate.
    """
    heightGroups = heightGroups or {}
    residualsPx = []
    for line in textLines:
        baseline = fit_baseline(line)
        if baseline is None:
            continue
        slope, intercept = baseline
        for letter in line.components:
            if letter.kind != "letter" or heightGroups.get(letter.componentId) in ("descender", "ascenderDescender"):
                continue
            centerXPx = letter.xPx + letter.widthPx / 2
            residualsPx.append(letter.yPx + letter.heightPx - (slope * centerXPx + intercept))
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


# ---------- all nine ----------

def compute_feature_measurements(inkMask: np.ndarray, textLines: list[TextLine],
                                 canvasHeightPx: Optional[int]) -> dict[str, Optional[float]]:
    """Return featureMeasurements with all nine canonical keys.

    canvasHeightPx is the page height before deskew expands the image, or None when the page edges
    weren't found (then the whole photo isn't a meaningful reference, so textHeightCanvasRatio is None).
    """
    xHeightPx = measure_x_height_px(inkMask, textLines)
    strokeWidthsPx = measure_stroke_widths_px(inkMask)
    letterGapsPx = find_letter_gaps_px(textLines)
    textHeightPx = measure_text_size_px(textLines)
    heightGroups = classify_height_groups(textLines)

    return {
        "textHeightCanvasRatio":  _ratio(textHeightPx, canvasHeightPx),
        "xHeightAscenderRatio":   measure_x_height_ascender_ratio(textLines, heightGroups),
        "baselineVariationRatio": _ratio(measure_baseline_variation_px(textLines, heightGroups), xHeightPx),
        "slantStdDeg":            measure_slant_std_deg(textLines),
        "letterHeightCv":         measure_letter_height_cv(textLines, heightGroups),
        "strokeContrastRatio":   measure_stroke_contrast_ratio(strokeWidthsPx),
        "strokeWidthRatio":   _ratio(measure_stroke_width_median_px(strokeWidthsPx), xHeightPx),
        "relativeLetterSpacing": measure_relative_letter_spacing(letterGapsPx, xHeightPx),
        "letterSpacingCv":       measure_letter_spacing_cv(letterGapsPx),
    }
