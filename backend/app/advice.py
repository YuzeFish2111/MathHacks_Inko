"""Weakest-first rule-based tips: at most three, each naming the measurement and the direction to change.

Each tip comes from a template keyed by (measurement, direction):
- sweet-spot measurements can be "low" (below the ideal range) or "high" (above it);
- decreasing measurements (variation) can only be "high" (too uneven).
shapeConsistency has three sources, so its tip describes whichever source scored worst.
"""
from typing import Optional

from .scoring import score_measurement
from .scoring_config import (FEATURE_IDS, FEATURE_SOURCES, SWEET_SPOT_CURVES,
                             MAX_ADVICE_ITEMS, ADVICE_MAX_FEATURE_SCORE)

# Placeholders: {value} is the measured value, {idealLow}/{idealHigh} the ideal range (sweet-spot curves only).
ADVICE_TEMPLATES = {
    ("textSizeMm", "low"): {
        "title": "Write a little bigger",
        "message": "Your letters are about {value} mm tall; the ideal range is {idealLow}-{idealHigh} mm.",
        "exercise": "Copy the sentence again, letting each letter fill more of the space between the lines.",
    },
    ("textSizeMm", "high"): {
        "title": "Write a little smaller",
        "message": "Your letters are about {value} mm tall; the ideal range is {idealLow}-{idealHigh} mm.",
        "exercise": "Copy the sentence again, keeping each letter inside the space between two lines.",
    },
    ("xHeightMm", "low"): {
        "title": "Make small letters taller",
        "message": "The bodies of your lowercase letters (a, e, o) are about {value} mm tall; "
                   "the ideal range is {idealLow}-{idealHigh} mm.",
        "exercise": "Practise rows of a, e, o and n, making them reach halfway up the line.",
    },
    ("xHeightMm", "high"): {
        "title": "Make small letters shorter",
        "message": "The bodies of your lowercase letters (a, e, o) are about {value} mm tall; "
                   "the ideal range is {idealLow}-{idealHigh} mm.",
        "exercise": "Practise rows of a, e, o and n, keeping them to half the line height so tall letters stand out.",
    },
    ("baselineVariationMm", "high"): {
        "title": "Keep letters on the line",
        "message": "Your letters drift up and down by about {value} mm from a straight baseline.",
        "exercise": "Write on lined paper and make the bottom of every letter touch the line.",
    },
    ("aspectRatioCv", "high"): {
        "title": "Keep letter widths even",
        "message": "Your letters' width-to-height proportions vary by {value}%.",
        "exercise": "Practise rows of the same letter (o, n, m), making each copy the same width.",
    },
    ("solidityCv", "high"): {
        "title": "Form letters the same way each time",
        "message": "The shapes of your letters vary by {value}%, so the same letter can look different.",
        "exercise": "Write each letter of the alphabet three times in a row and check that the copies match.",
    },
    ("slantStdDeg", "high"): {
        "title": "Keep a steady slant",
        "message": "The lean of your letters varies by about {value} degrees.",
        "exercise": "Draw a few light parallel guide lines at your preferred angle and write along them.",
    },
    ("strokeContrastRatio", "high"): {
        "title": "Keep pen pressure even",
        "message": "Your thickest strokes are {value} times as wide as your thinnest.",
        "exercise": "Write slowly with steady, light pressure, keeping the pen at the same angle.",
    },
    ("strokeWidthMedianMm", "low"): {
        "title": "Use a darker or thicker pen",
        "message": "Your strokes are about {value} mm wide; the ideal range is {idealLow}-{idealHigh} mm.",
        "exercise": "Try a medium ballpoint or gel pen, or press slightly harder.",
    },
    ("strokeWidthMedianMm", "high"): {
        "title": "Use a finer pen",
        "message": "Your strokes are about {value} mm wide; the ideal range is {idealLow}-{idealHigh} mm.",
        "exercise": "Try a fine-tip pen or sharpened pencil so letters with holes (a, e, o) stay open.",
    },
    ("relativeLetterSpacing", "low"): {
        "title": "Leave more space between letters",
        "message": "The gaps between your letters are {value}% of a letter's height; "
                   "the ideal range is {idealLow}-{idealHigh}%.",
        "exercise": "Practise leaving about the width of a pencil tip between letters in each word.",
    },
    ("relativeLetterSpacing", "high"): {
        "title": "Keep letters in a word closer",
        "message": "The gaps between your letters are {value}% of a letter's height; "
                   "the ideal range is {idealLow}-{idealHigh}%.",
        "exercise": "Practise writing each word as a tight group, with clearly bigger gaps between words.",
    },
    ("letterSpacingCv", "high"): {
        "title": "Make letter gaps more even",
        "message": "Your letter gaps vary by {value}%.",
        "exercise": "Practise keeping a similar pencil-width gap between letters.",
    },
}

# How each measurement's value is shown in a message: (multiplier, decimal places)
DISPLAY_FORMATS = {
    "textSizeMm": (1, 1), "xHeightMm": (1, 1), "baselineVariationMm": (1, 1),
    "aspectRatioCv": (100, 0), "solidityCv": (100, 0), "slantStdDeg": (1, 0),
    "strokeContrastRatio": (1, 1), "strokeWidthMedianMm": (1, 2),
    "relativeLetterSpacing": (100, 0), "letterSpacingCv": (100, 0),
}


def _format_value(measurementName: str, value: float) -> str:
    multiplier, decimals = DISPLAY_FORMATS[measurementName]
    return f"{value * multiplier:.{decimals}f}"


def _weakest_source(featureId: str, featureMeasurements: dict[str, Optional[float]]) -> Optional[str]:
    """The source measurement with the lowest score (only differs from the sole source for shapeConsistency)."""
    scoredSources = [(score_measurement(name, featureMeasurements.get(name)), name)
                     for name in FEATURE_SOURCES[featureId]]
    scoredSources = [(score, name) for score, name in scoredSources if score is not None]
    return min(scoredSources)[1] if scoredSources else None


def _direction(measurementName: str, value: float) -> str:
    """'low' if below a sweet-spot range, otherwise 'high' (too big, or too much variation)."""
    if measurementName in SWEET_SPOT_CURVES:
        _, idealLow, _, _ = SWEET_SPOT_CURVES[measurementName]
        return "low" if value < idealLow else "high"
    return "high"


def build_advice_item(featureId: str, featureMeasurements: dict[str, Optional[float]]) -> Optional[dict]:
    """One tip for a feature, filled in with the measured value, or None if it cannot be described."""
    measurementName = _weakest_source(featureId, featureMeasurements)
    if measurementName is None:
        return None
    value = featureMeasurements[measurementName]
    template = ADVICE_TEMPLATES[(measurementName, _direction(measurementName, value))]

    placeholders = {"value": _format_value(measurementName, value)}
    if measurementName in SWEET_SPOT_CURVES:
        _, idealLow, idealHigh, _ = SWEET_SPOT_CURVES[measurementName]
        placeholders["idealLow"] = _format_value(measurementName, idealLow)
        placeholders["idealHigh"] = _format_value(measurementName, idealHigh)

    return {
        "featureId": featureId,
        "title": template["title"],
        "message": template["message"].format(**placeholders),
        "exercise": template["exercise"],
    }


def generate_advice(featureScores: dict[str, Optional[float]],
                    featureMeasurements: dict[str, Optional[float]]) -> list[dict]:
    """Up to MAX_ADVICE_ITEMS tips for the weakest features, weakest first.

    Missing features (score None) and features scoring above ADVICE_MAX_FEATURE_SCORE get no tip.
    Ties keep the FEATURE_IDS order, so the result is deterministic.
    """
    weakFeatureIds = sorted(
        (featureId for featureId in FEATURE_IDS
         if featureScores.get(featureId) is not None and featureScores[featureId] <= ADVICE_MAX_FEATURE_SCORE),
        key=lambda featureId: featureScores[featureId])

    advice = []
    for featureId in weakFeatureIds:
        adviceItem = build_advice_item(featureId, featureMeasurements)
        if adviceItem is not None:
            advice.append(adviceItem)
        if len(advice) == MAX_ADVICE_ITEMS:
            break
    return advice
