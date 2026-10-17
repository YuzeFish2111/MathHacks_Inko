"""issueFeatureIds: which overlay boxes show a problem, so the browser can highlight them.

Two kinds of mark:
- Element problems, judged against the writer's own typical letter or gap:
    baselineConsistency  a letter's bottom drifts off its line's fitted baseline
    shapeConsistency     a letter leans much more or less than the typical letter
    spacingConsistency   a letter gap is much wider or narrower than the typical gap
    letterSpacing        a letter gap is outside the ideal range, or letters are joined into a cluster
    ocrReadability       a letter sits inside a word the OCR model read with low confidence
- Whole-page problems: size, x-height and stroke can't be pinned on one letter, so when one of those
  features scores at or below ISSUE_MAX_FEATURE_SCORE, every letter is marked with it.
All distances are compared as multiples of the x-height, so the rules work at any writing size.
"""
from typing import Optional

import numpy as np

from .image_pipeline import TextLine
from .measurements import fit_baseline, letter_slant_deg
from .scoring_config import (FEATURE_IDS, SWEET_SPOT_CURVES, ISSUE_MAX_FEATURE_SCORE,
                             ISSUE_BASELINE_OFFSET_RATIO, ISSUE_SLANT_DEVIATION_DEG, ISSUE_GAP_DEVIATION_RATIO,
                             ISSUE_OCR_MIN_CONFIDENCE)

WHOLE_PAGE_FEATURE_IDS = ("textSize", "xHeight", "strokeContrast", "strokeWeight")


def _in_feature_order(featureIds: set[str]) -> list[str]:
    return [featureId for featureId in FEATURE_IDS if featureId in featureIds]


def find_component_issues(textLines: list[TextLine], xHeightPx: Optional[float],
                          featureScores: dict[str, Optional[float]],
                          ocrDetections: Optional[list] = None) -> dict[str, list[str]]:
    """componentId -> issueFeatureIds for every component (empty list when it has no problem).

    ocrDetections: EasyOCR (boundingBox, text, confidence) tuples in the same image's pixels, if OCR ran.
    """
    issues = {component.componentId: set() for line in textLines for component in line.components}
    letters = [component for line in textLines for component in line.components if component.kind == "letter"]

    # Whole-page problems: mark every letter
    weakPageFeatures = {featureId for featureId in WHOLE_PAGE_FEATURE_IDS
                        if featureScores.get(featureId) is not None
                        and featureScores[featureId] <= ISSUE_MAX_FEATURE_SCORE}
    for letter in letters:
        issues[letter.componentId] |= weakPageFeatures

    # Joined letters: the writing has no gap there at all
    for line in textLines:
        for component in line.components:
            if component.kind == "cluster":
                issues[component.componentId].add("letterSpacing")

    # Baseline: a letter floats (bottom above the line) or has sunk as a whole (bottom AND top low).
    # A descender (g, p, y) only drops its tail: its top still sits at the x-height line, so it isn't marked.
    if xHeightPx:
        for line in textLines:
            baseline = fit_baseline(line)
            if baseline is None:
                continue
            slope, intercept = baseline
            lineLetters = [component for component in line.components if component.kind == "letter"]

            def height_above_baseline_px(component):
                return slope * (component.xPx + component.widthPx / 2) + intercept - component.yPx

            # Typical top of a letter in this line: most letters are x-height letters, so the median
            # marks the x-height line (more robust than baseline - xHeightPx on unusual shapes)
            typicalTopPx = float(np.median([height_above_baseline_px(letter) for letter in lineLetters]))
            for component in lineLetters:
                baselineYPx = slope * (component.xPx + component.widthPx / 2) + intercept
                bottomOffsetRatio = (component.yPx + component.heightPx - baselineYPx) / xHeightPx
                topOffsetRatio = (typicalTopPx - height_above_baseline_px(component)) / xHeightPx    # + = lower
                isFloating = bottomOffsetRatio < -ISSUE_BASELINE_OFFSET_RATIO
                isSunk = bottomOffsetRatio > ISSUE_BASELINE_OFFSET_RATIO and topOffsetRatio > ISSUE_BASELINE_OFFSET_RATIO
                if isFloating or isSunk:
                    issues[component.componentId].add("baselineConsistency")

    # Slant: compare each letter with the median letter
    slantsDeg = {letter.componentId: letter_slant_deg(letter) for letter in letters}
    knownSlantsDeg = [slantDeg for slantDeg in slantsDeg.values() if slantDeg is not None]
    if knownSlantsDeg:
        medianSlantDeg = float(np.median(knownSlantsDeg))
        for componentId, slantDeg in slantsDeg.items():
            if slantDeg is not None and abs(slantDeg - medianSlantDeg) > ISSUE_SLANT_DEVIATION_DEG:
                issues[componentId].add("shapeConsistency")

    # OCR: letters whose centre lies inside a word the model read with low confidence
    for boundingBox, _, confidence in ocrDetections or []:
        if confidence >= ISSUE_OCR_MIN_CONFIDENCE:
            continue
        boxXs, boxYs = [point[0] for point in boundingBox], [point[1] for point in boundingBox]
        for line in textLines:
            for component in line.components:
                centerXPx = component.xPx + component.widthPx / 2
                centerYPx = component.yPx + component.heightPx / 2
                if min(boxXs) <= centerXPx <= max(boxXs) and min(boxYs) <= centerYPx <= max(boxYs):
                    issues[component.componentId].add("ocrReadability")

    return {componentId: _in_feature_order(featureIds) for componentId, featureIds in issues.items()}


def find_gap_issues(gaps: list[dict], xHeightPx: Optional[float]) -> list[list[str]]:
    """issueFeatureIds for each gap from measurements.find_gaps, in the same order. Word gaps are never marked."""
    letterGapWidthsPx = [gap["widthPx"] for gap in gaps if gap["kind"] == "letter"]
    if not xHeightPx or not letterGapWidthsPx:
        return [[] for _ in gaps]

    medianGapPx = float(np.median(letterGapWidthsPx))
    _, idealLowRatio, idealHighRatio, _ = SWEET_SPOT_CURVES["relativeLetterSpacing"]
    gapIssues = []
    for gap in gaps:
        featureIds = set()
        if gap["kind"] == "letter":
            gapRatio = gap["widthPx"] / xHeightPx
            if not idealLowRatio <= gapRatio <= idealHighRatio:
                featureIds.add("letterSpacing")
            if abs(gap["widthPx"] - medianGapPx) / xHeightPx > ISSUE_GAP_DEVIATION_RATIO:
                featureIds.add("spacingConsistency")
        gapIssues.append(_in_feature_order(featureIds))
    return gapIssues
