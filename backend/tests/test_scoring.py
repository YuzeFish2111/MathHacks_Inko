import math

from app.scoring import (sweet_spot_score, decreasing_score, increasing_score, score_measurement,
                         compute_feature_scores, compute_legibility_score, score_label, score_measurements)
from app.scoring_config import (FEATURE_IDS, FEATURE_SOURCES, FEATURE_WEIGHTS,
                                SWEET_SPOT_CURVES, DECREASING_CURVES, INCREASING_CURVES)

TEXT_SIZE_CURVE = (1.5, 3.0, 7.0, 12.0)


def test_sweet_spot_score_trapezoid():
    assert sweet_spot_score(5.0, *TEXT_SIZE_CURVE) == 1.0     # inside the ideal range
    assert sweet_spot_score(2.25, *TEXT_SIZE_CURVE) == 0.5    # halfway up the rising edge
    assert sweet_spot_score(9.5, *TEXT_SIZE_CURVE) == 0.5     # halfway down the falling edge
    assert sweet_spot_score(13, *TEXT_SIZE_CURVE) == 0.0      # beyond d
    assert sweet_spot_score(1.5, *TEXT_SIZE_CURVE) == 0.0     # exactly a
    assert sweet_spot_score(3.0, *TEXT_SIZE_CURVE) == 1.0     # exactly b
    assert sweet_spot_score(7.0, *TEXT_SIZE_CURVE) == 1.0     # exactly c


def test_decreasing_score_line():
    assert decreasing_score(1.0, 2.0, 20.0) == 1.0
    assert decreasing_score(2.0, 2.0, 20.0) == 1.0
    assert decreasing_score(11.0, 2.0, 20.0) == 0.5
    assert decreasing_score(20.0, 2.0, 20.0) == 0.0
    assert decreasing_score(25.0, 2.0, 20.0) == 0.0


def test_missing_values_stay_null():
    for missing in (None, math.nan, math.inf):
        assert sweet_spot_score(missing, *TEXT_SIZE_CURVE) is None
        assert decreasing_score(missing, 2.0, 20.0) is None


# ---------- feature scores, legibilityScore, scoreLabel ----------

PERFECT_MEASUREMENTS = {
    "textSizeMm": 5.0, "xHeightMm": 3.0, "baselineVariationMm": 0.2, "aspectRatioCv": 0.05,
    "solidityCv": 0.02, "slantStdDeg": 1.0, "strokeContrastRatio": 1.1, "strokeWidthMedianMm": 0.5,
    "relativeLetterSpacing": 0.3, "letterSpacingCv": 0.1, "ocrConfidencePct": 95.0,
}


def test_every_source_measurement_has_exactly_one_curve():
    sources = {name for names in FEATURE_SOURCES.values() for name in names}
    curves = [set(SWEET_SPOT_CURVES), set(DECREASING_CURVES), set(INCREASING_CURVES)]
    assert sources == set.union(*curves)
    assert sum(len(curve) for curve in curves) == len(sources)        # no measurement has two curves
    assert set(FEATURE_SOURCES) == set(FEATURE_IDS) == set(FEATURE_WEIGHTS)


def test_score_measurement_picks_the_right_curve():
    assert score_measurement("textSizeMm", 2.25) == 0.5            # sweet-spot curve
    assert score_measurement("slantStdDeg", 11.0) == 0.5           # decreasing curve


def test_perfect_writing_scores_100():
    result = score_measurements(PERFECT_MEASUREMENTS)
    assert all(score == 1.0 for score in result["featureScores"].values())
    assert result["legibilityScore"] == 100
    assert result["scoreLabel"] == "Very legible"
    assert result["missingFeatureIds"] == []
    assert abs(sum(result["featureWeights"].values()) - 1) < 1e-9


def test_shape_consistency_averages_only_available_sources():
    measurements = dict(PERFECT_MEASUREMENTS, aspectRatioCv=0.45, solidityCv=None)   # 0.5 and missing
    # slantStdDeg 1.0 -> 1.0, aspectRatioCv 0.45 -> 0.5, solidityCv ignored -> mean 0.75
    assert compute_feature_scores(measurements)["shapeConsistency"] == 0.75


def test_missing_features_are_excluded_not_counted_as_zero_or_perfect():
    measurements = dict(PERFECT_MEASUREMENTS, textSizeMm=None, xHeightMm=None, slantStdDeg=25.0)
    featureScores = compute_feature_scores(measurements)
    legibilityScore, featureWeights, missingFeatureIds = compute_legibility_score(featureScores)

    assert missingFeatureIds == ["textSize", "xHeight"]
    assert set(featureWeights) == set(FEATURE_IDS) - {"textSize", "xHeight"}
    assert all(abs(weight - 1 / 7) < 1e-9 for weight in featureWeights.values())   # 1/9 renormalized over 7
    # shapeConsistency = mean(1, 1, 0) = 2/3; the other six are 1 -> (6 + 2/3) / 7 = 95.2
    assert legibilityScore == 95


def test_no_features_gives_null_score():
    result = score_measurements({name: None for name in PERFECT_MEASUREMENTS})
    assert result["legibilityScore"] is None
    assert result["scoreLabel"] is None
    assert result["featureWeights"] == {}
    assert result["missingFeatureIds"] == list(FEATURE_IDS)
    assert all(score is None for score in result["featureScores"].values())


def test_missing_measurement_key_is_treated_as_null():
    assert compute_feature_scores({})["textSize"] is None


def test_score_label_band_edges():
    assert score_label(100) == "Very legible"
    assert score_label(85) == "Very legible"
    assert score_label(84) == "Readable"
    assert score_label(70) == "Readable"
    assert score_label(69) == "Some difficulty"
    assert score_label(50) == "Some difficulty"
    assert score_label(49) == "Hard to read"
    assert score_label(0) == "Hard to read"
    assert score_label(None) is None


def test_score_rounds_half_up():
    featureScores = {featureId: 0.845 for featureId in FEATURE_IDS}
    assert compute_legibility_score(featureScores)[0] == 85     # 84.5 -> 85, label matches the shown number


def test_increasing_score_line():
    assert increasing_score(20.0, 30.0, 85.0) == 0.0
    assert increasing_score(57.5, 30.0, 85.0) == 0.5
    assert increasing_score(90.0, 30.0, 85.0) == 1.0
    assert increasing_score(None, 30.0, 85.0) is None
    assert score_measurement("ocrConfidencePct", 57.5) == 0.5


def test_unavailable_ocr_leaves_the_other_features_sharing_the_weight():
    result = score_measurements(dict(PERFECT_MEASUREMENTS, ocrConfidencePct=None))
    assert result["missingFeatureIds"] == ["ocrReadability"]
    assert result["featureScores"]["ocrReadability"] is None
    assert len(result["featureWeights"]) == 8 and abs(sum(result["featureWeights"].values()) - 1) < 1e-9
    assert result["legibilityScore"] == 100
