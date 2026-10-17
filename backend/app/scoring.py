"""Turn the nine raw measurements into nine 0-1 feature scores, one 0-100 legibilityScore and a label.

1. Each measurement goes through its curve (scoring_config.py) to a 0-1 score.
2. Each feature takes its measurement's score (a feature with several sources would average them).
3. legibilityScore = 100 x weighted average of the available feature scores. Missing features are
   left out (weights rescaled to sum to 1) rather than counted as 0 or as perfect.
"""
import math

from typing import Optional
from .scoring_config import (FEATURE_IDS, FEATURE_WEIGHTS, FEATURE_SOURCES,
                             SWEET_SPOT_CURVES, DECREASING_CURVES, INCREASING_CURVES, SCORE_BANDS)


def _is_missing(value: Optional[float]) -> bool:
    """True when a measurement is unknown (None) or not a usable number (NaN/inf)."""
    return value is None or not math.isfinite(value)


def sweet_spot_score(value: Optional[float], a: float, b: float, c: float, d: float) -> Optional[float]:
    """Trapezoid curve: 0 outside (a, d), rises a->b, 1 on [b, c], falls c->d."""
    if _is_missing(value):
        return None
    if value <= a or value >= d:
        return 0.0
    if b <= value <= c:
        return 1.0
    if value < b:
        return (value - a) / (b - a)    # rising edge
    return (d - value) / (d - c)        # falling edge


def decreasing_score(value: Optional[float], v0: float, v1: float) -> Optional[float]:
    """Linear decrease: 1 at or below v0, 0 at or above v1."""
    if _is_missing(value):
        return None
    if value <= v0:
        return 1.0
    if value >= v1:
        return 0.0
    return (v1 - value) / (v1 - v0)


def increasing_score(value: Optional[float], v0: float, v1: float) -> Optional[float]:
    """Linear increase: 0 at or below v0, 1 at or above v1."""
    if _is_missing(value):
        return None
    if value <= v0:
        return 0.0
    if value >= v1:
        return 1.0
    return (value - v0) / (v1 - v0)


def score_measurement(measurementName: str, value: Optional[float]) -> Optional[float]:
    """Score one raw measurement 0-1 with the curve configured for it in scoring_config.py."""
    if measurementName in SWEET_SPOT_CURVES:
        return sweet_spot_score(value, *SWEET_SPOT_CURVES[measurementName])
    if measurementName in DECREASING_CURVES:
        return decreasing_score(value, *DECREASING_CURVES[measurementName])
    if measurementName in INCREASING_CURVES:
        return increasing_score(value, *INCREASING_CURVES[measurementName])
    raise KeyError(f"No curve configured for measurement {measurementName!r}")


def compute_feature_scores(featureMeasurements: dict[str, Optional[float]]) -> dict[str, Optional[float]]:
    """featureScores: featureId -> 0-1 normalizedScore, or None if none of its sources were measured.

    A feature with several sources (shapeConsistency) is the mean of the sources that are available.
    Every featureId is always present.
    """
    featureScores = {}
    for featureId in FEATURE_IDS:
        sourceScores = [score_measurement(name, featureMeasurements.get(name))
                        for name in FEATURE_SOURCES[featureId]]
        availableScores = [sourceScore for sourceScore in sourceScores if sourceScore is not None]
        featureScores[featureId] = sum(availableScores) / len(availableScores) if availableScores else None
    return featureScores


def compute_legibility_score(featureScores: dict[str, Optional[float]]
                             ) -> tuple[Optional[int], dict[str, float], list[str]]:
    """Weighted 0-100 score from the available features only.

    Returns (legibilityScore, featureWeights, missingFeatureIds):
    - featureWeights holds only the features used, renormalized to sum to 1;
    - missingFeatureIds lists features whose score is None (they count as neither perfect nor zero);
    - legibilityScore is rounded to a whole number for display, or None if no feature is available.
    """
    missingFeatureIds = [featureId for featureId in FEATURE_IDS if featureScores.get(featureId) is None]
    availableIds = [featureId for featureId in FEATURE_IDS if featureId not in missingFeatureIds]
    usedWeightTotal = sum(FEATURE_WEIGHTS[featureId] for featureId in availableIds)
    if usedWeightTotal <= 0:
        return None, {}, missingFeatureIds

    featureWeights = {featureId: FEATURE_WEIGHTS[featureId] / usedWeightTotal for featureId in availableIds}
    weightedScore = sum(featureWeights[featureId] * featureScores[featureId] for featureId in availableIds)
    legibilityScore = math.floor(100 * weightedScore + 0.5)    # round half up (Python's round() rounds half to even)
    return legibilityScore, featureWeights, missingFeatureIds


def score_label(legibilityScore: Optional[float]) -> Optional[str]:
    """scoreLabel: the first band in SCORE_BANDS whose minimum the score reaches."""
    if legibilityScore is None:
        return None
    for minimumScore, label in SCORE_BANDS:
        if legibilityScore >= minimumScore:
            return label
    return SCORE_BANDS[-1][1]


def score_measurements(featureMeasurements: dict[str, Optional[float]]) -> dict:
    """Everything scoring adds to the response, under its contract names."""
    featureScores = compute_feature_scores(featureMeasurements)
    legibilityScore, featureWeights, missingFeatureIds = compute_legibility_score(featureScores)
    return {
        "featureScores": featureScores,
        "featureWeights": featureWeights,
        "missingFeatureIds": missingFeatureIds,
        "legibilityScore": legibilityScore,
        "scoreLabel": score_label(legibilityScore),
    }


