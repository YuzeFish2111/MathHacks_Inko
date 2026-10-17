import re
import string

from app.advice import ADVICE_TEMPLATES, DISPLAY_FORMATS, build_advice_item, generate_advice
from app.schemas import AdviceItem
from app.scoring import compute_feature_scores
from app.scoring_config import SWEET_SPOT_CURVES, DECREASING_CURVES, FEATURE_SOURCES, MAX_ADVICE_ITEMS

PERFECT_MEASUREMENTS = {
    "textSizeMm": 5.0, "xHeightMm": 3.0, "baselineVariationMm": 0.2, "aspectRatioCv": 0.05,
    "solidityCv": 0.02, "slantStdDeg": 1.0, "strokeContrastRatio": 1.1, "strokeWidthMedianMm": 0.5,
    "relativeLetterSpacing": 0.3, "letterSpacingCv": 0.1,
}


def advice_for(**changes):
    measurements = dict(PERFECT_MEASUREMENTS, **changes)
    return generate_advice(compute_feature_scores(measurements), measurements)


def test_every_measurement_and_direction_has_a_template():
    expected = {(name, direction) for name in SWEET_SPOT_CURVES for direction in ("low", "high")}
    expected |= {(name, "high") for name in DECREASING_CURVES}
    assert set(ADVICE_TEMPLATES) == expected
    assert set(DISPLAY_FORMATS) == set(SWEET_SPOT_CURVES) | set(DECREASING_CURVES)


def test_templates_only_use_known_placeholders():
    for (name, _), template in ADVICE_TEMPLATES.items():
        fields = {field for _, field, _, _ in string.Formatter().parse(template["message"]) if field}
        allowed = {"value", "idealLow", "idealHigh"} if name in SWEET_SPOT_CURVES else {"value"}
        assert fields <= allowed, name


def test_perfect_writing_gets_no_advice():
    assert advice_for() == []


def test_sweet_spot_direction_low_and_high():
    small = advice_for(textSizeMm=2.0)
    assert small[0]["featureId"] == "textSize" and small[0]["title"] == "Write a little bigger"
    assert "2.0 mm" in small[0]["message"] and "3.0-7.0 mm" in small[0]["message"]

    big = advice_for(textSizeMm=10.0)
    assert big[0]["title"] == "Write a little smaller"


def test_message_includes_the_measured_value_as_a_percent():
    tip = advice_for(letterSpacingCv=0.38)[0]
    assert tip["featureId"] == "spacingConsistency"
    assert tip["message"] == "Your letter gaps vary by 38%."


def test_shape_consistency_describes_its_weakest_source():
    tip = advice_for(slantStdDeg=15.0)[0]                   # aspect and solidity are perfect
    assert tip["featureId"] == "shapeConsistency"
    assert tip["title"] == "Keep a steady slant"


def test_weakest_first_and_at_most_three():
    advice = advice_for(textSizeMm=1.0,               # score 0
                        baselineVariationMm=1.95,     # score ~0.25
                        letterSpacingCv=0.575,        # score 0.5
                        strokeContrastRatio=2.6)      # score 0.5 (ties keep FEATURE_IDS order)
    assert len(advice) == MAX_ADVICE_ITEMS
    assert [tip["featureId"] for tip in advice] == ["textSize", "baselineConsistency", "strokeContrast"]


def test_missing_features_get_no_advice():
    assert advice_for(textSizeMm=None, letterSpacingCv=None) == []
    assert build_advice_item("textSize", {"textSizeMm": None}) is None


def test_every_template_produces_a_valid_advice_item():
    worst = {"low": 0.0001, "high": 1000.0}
    for (name, direction) in ADVICE_TEMPLATES:
        featureId = next(f for f, sources in FEATURE_SOURCES.items() if name in sources)
        tip = build_advice_item(featureId, dict(PERFECT_MEASUREMENTS, **{name: worst[direction]}))
        AdviceItem.model_validate(tip)
        assert not re.search(r"[{}]", tip["message"]), name    # every placeholder was filled
