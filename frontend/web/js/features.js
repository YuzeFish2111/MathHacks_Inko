// The eight features the analysis backend scores (shared/analysis-contract.md, schema 2.1).
// featureIds and measurement names are the contract's, never renamed. Ideal ranges are not
// copied here: they come from backend/app/scoring_config.py through GET /api/scoring-model.

/** Display order when scores tie, and the order of the contract's featureId list. */
export const FEATURE_IDS = [
  "textSize", "xHeight", "baselineConsistency", "shapeConsistency",
  "strokeContrast", "strokeWeight", "letterSpacing", "spacingConsistency",
];

// unit: how a raw measurement is shown. "pct" = fraction shown as %, "deg" = degrees,
// "times" = a ratio, with `of` saying what it is a multiple of.
export const MEASUREMENTS = {
  textHeightCanvasRatio: { label: "Letter height", unit: "pct", of: "of the page height" },
  xHeightAscenderRatio: { label: "Small / tall letters", unit: "times", of: "of the tall-letter height" },
  baselineVariationRatio: { label: "Wobble off the line", unit: "times", of: "of the small-letter height" },
  slantStdDeg: { label: "Slant spread", unit: "deg" },
  letterHeightCv: { label: "Height spread", unit: "pct" },
  strokeContrastRatio: { label: "Thick / thin strokes", unit: "times" },
  strokeWidthRatio: { label: "Stroke width", unit: "times", of: "of the small-letter height" },
  relativeLetterSpacing: { label: "Letter gap", unit: "times", of: "of the small-letter height" },
  letterSpacingCv: { label: "Gap spread", unit: "pct" },
};

export const FEATURES = {
  textSize: { label: "Letter size", measurements: ["textHeightCanvasRatio"], worksheet: "size" },
  xHeight: { label: "Small-letter height", measurements: ["xHeightAscenderRatio"], worksheet: "size" },
  baselineConsistency: { label: "Staying on the line", measurements: ["baselineVariationRatio"], worksheet: "alignment" },
  shapeConsistency: { label: "Consistent shape", measurements: ["slantStdDeg", "letterHeightCv"], worksheet: "slant" },
  strokeContrast: { label: "Even pen pressure", measurements: ["strokeContrastRatio"], worksheet: null },
  strokeWeight: { label: "Pen thickness", measurements: ["strokeWidthRatio"], worksheet: null },
  letterSpacing: { label: "Space between letters", measurements: ["relativeLetterSpacing"], worksheet: "spacing" },
  spacingConsistency: { label: "Even spacing", measurements: ["letterSpacingCv"], worksheet: "spacing" },
};

/** Marked on every letter when they score low, so they are drawn as a page-wide tint, not as boxes. */
export const PAGE_WIDE_FEATURES = new Set(["textSize", "xHeight", "strokeWeight", "strokeContrast"]);

export const featureLabel = (featureId) => (FEATURES[featureId] && FEATURES[featureId].label) || featureId;

function trim(n, digits) {
  return String(Number(n.toFixed(digits)));
}

function formatNumber(value, unit) {
  if (unit === "pct") return `${trim(value * 100, value < 0.1 ? 1 : 0)}%`;
  if (unit === "deg") return `${trim(value, 1)}°`;
  return `${trim(value, 2)}×`;
}

/** "0.16× of the small-letter height", or "Not measured" for null (0 is a real value). */
export function formatMeasurement(name, value) {
  if (value === null || value === undefined) return "Not measured";
  const info = MEASUREMENTS[name] || { unit: "times" };
  return `${formatNumber(value, info.unit)}${info.of ? ` ${info.of}` : ""}`;
}

/** The ideal range from a backend curve: the flat top of a sweet-spot curve, or "at most v0". */
export function idealRange(name, model) {
  const curve = model && model.curves && model.curves[name];
  if (!curve) return null;
  const unit = (MEASUREMENTS[name] || { unit: "times" }).unit;
  if (curve.kind === "decreasing") return `${formatNumber(curve.v0, unit)} or less`;
  return `${formatNumber(curve.b, unit)} to ${formatNumber(curve.c, unit)}`;
}

let modelPromise = null;

/** GET /api/scoring-model once; resolves to null if it can't be loaded (ideal ranges are then hidden). */
export function loadScoringModel() {
  if (!modelPromise) {
    modelPromise = fetch("/api/scoring-model", { credentials: "same-origin" })
      .then((res) => (res.ok ? res.json() : null))
      .catch(() => null)
      .then((model) => { if (!model) modelPromise = null; return model; });
  }
  return modelPromise;
}
