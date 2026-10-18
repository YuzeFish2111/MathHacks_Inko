// The scoring maths in the browser, so Inko can show and simulate how the score is built.
// Ported exactly from backend/app/scoring.py (curves, weighted mean, rounding). Curves, sources
// and weights always come from GET /api/scoring-model (backend/app/scoring_config.py), never copied.

/** One measurement's 0-1 score on its curve, or null if unknown (same as scoring.py). */
export function scoreOnCurve(value, curve) {
  if (value === null || value === undefined || !Number.isFinite(value) || !curve) return null;
  if (curve.kind === "decreasing") {
    const { v0, v1 } = curve;
    if (value <= v0) return 1;
    if (value >= v1) return 0;
    return (v1 - value) / (v1 - v0);
  }
  const { a, b, c, d } = curve;
  if (value <= a || value >= d) return 0;
  if (value >= b && value <= c) return 1;
  return value < b ? (value - a) / (b - a) : (d - value) / (d - c);
}

/** featureId -> 0-1 score: the mean of its available source scores (shapeConsistency has two). */
export function featureScoresFrom(measurements, model) {
  const scores = {};
  for (const [featureId, sources] of Object.entries(model.featureSources)) {
    const known = sources.map((name) => scoreOnCurve(measurements[name], model.curves[name])).filter((s) => s !== null);
    scores[featureId] = known.length ? known.reduce((sum, s) => sum + s, 0) / known.length : null;
  }
  return scores;
}

/** Weighted mean over available features only, weights rescaled to sum to 1, rounded half up.
 *  Returns { score, weightsUsed, exact } (score null when nothing could be measured). */
export function legibilityFrom(featureScores, weights) {
  const available = Object.keys(featureScores).filter((k) => featureScores[k] !== null && weights[k] !== undefined);
  const total = available.reduce((sum, k) => sum + weights[k], 0);
  if (!(total > 0)) return { score: null, weightsUsed: {}, exact: null };
  const weightsUsed = Object.fromEntries(available.map((k) => [k, weights[k] / total]));
  const exact = 100 * available.reduce((sum, k) => sum + weightsUsed[k] * featureScores[k], 0);
  return { score: Math.floor(exact + 0.5), weightsUsed, exact };
}

/** scoreLabel: the first band whose minimum the score reaches (bands from the scoring model). */
export function labelFor(score, model) {
  if (score === null || !model) return null;
  const bands = [...model.scoreBands].sort((p, q) => q.minScore - p.minScore);
  const band = bands.find((b) => score >= b.minScore) || bands[bands.length - 1];
  return band ? band.label : null;
}

// ---------- robust statistics (same estimators as backend/app/measurements.py) ----------

export function median(values) {
  const sorted = [...values].sort((p, q) => p - q), mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

/** Theil-Sen: slope = median of all pairwise slopes; intercept = median(y) - slope * median(x),
 *  the same rule as SciPy's theilslopes, which the backend uses. */
export function theilSen(xs, ys) {
  const slopes = [];
  for (let i = 0; i < xs.length; i++)
    for (let j = i + 1; j < xs.length; j++)
      if (xs[j] !== xs[i]) slopes.push((ys[j] - ys[i]) / (xs[j] - xs[i]));
  const slope = slopes.length ? median(slopes) : 0;
  return { slope, intercept: median(ys) - slope * median(xs) };
}

/** Ordinary least squares, the usual best-fit line, for comparison. */
export function leastSquares(xs, ys) {
  const meanX = xs.reduce((s, x) => s + x, 0) / xs.length;
  const meanY = ys.reduce((s, y) => s + y, 0) / ys.length;
  let covariance = 0, variance = 0;
  xs.forEach((x, i) => { covariance += (x - meanX) * (ys[i] - meanY); variance += (x - meanX) ** 2; });
  const slope = variance ? covariance / variance : 0;
  return { slope, intercept: meanY - slope * meanX };
}

/** Robust standard deviation: 1.4826 x median absolute deviation (equals the SD for normal data). */
export function robustSpread(values) {
  const m = median(values);
  return 1.4826 * median(values.map((v) => Math.abs(v - m)));
}

/** Plain (population) standard deviation, for comparison with robustSpread. */
export function standardDeviation(values) {
  const mean = values.reduce((s, v) => s + v, 0) / values.length;
  return Math.sqrt(values.reduce((s, v) => s + (v - mean) ** 2, 0) / values.length);
}
