import { h } from "../ui.js";
import { FEATURES, FEATURE_IDS, featureLabel, formatMeasurement, idealRange, MEASUREMENTS } from "../features.js";

// `scores` below are the 0-100 summary Inko keeps per scan (featureScores × 100, null when a
// feature couldn't be measured). The full backend response is `result.analysis`.

export const factorLabel = featureLabel;

/** Feature keys that have a number, in contract order (null = not measured, left out). */
export function factorKeys(scores = {}) {
  const known = FEATURE_IDS.filter((k) => typeof scores[k] === "number");
  const extra = Object.keys(scores).filter((k) => !FEATURE_IDS.includes(k) && typeof scores[k] === "number");
  return known.concat(extra);
}

export function weakestFactor(scores = {}) {
  const keys = factorKeys(scores);
  if (!keys.length) return null;
  return keys.reduce((a, b) => (scores[b] < scores[a] ? b : a));
}

export function strongestFactor(scores = {}) {
  const keys = factorKeys(scores);
  if (!keys.length) return null;
  return keys.reduce((a, b) => (scores[b] > scores[a] ? b : a));
}

function scoreRing(score) {
  const r = 54, c = 2 * Math.PI * r;
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 132 132");
  svg.setAttribute("aria-hidden", "true");
  for (const [cls, dash] of [["track", 0], ["value", 1]]) {
    const circle = document.createElementNS(ns, "circle");
    circle.setAttribute("cx", "66"); circle.setAttribute("cy", "66"); circle.setAttribute("r", String(r));
    circle.setAttribute("fill", "none"); circle.setAttribute("stroke-width", "12");
    circle.setAttribute("class", cls);
    if (dash) {
      circle.setAttribute("stroke-linecap", "round");
      circle.setAttribute("stroke-dasharray", String(c));
      circle.setAttribute("stroke-dashoffset", String(c));
      requestAnimationFrame(() => requestAnimationFrame(() =>
        circle.setAttribute("stroke-dashoffset", String(c * (1 - (score || 0) / 100)))));
    }
    svg.append(circle);
  }
  return h("div", { class: "score-ring", role: "img", "aria-label": score === null ? "No overall score" : `Overall legibility ${score} out of 100` },
    svg, h("div", { class: "num" }, h("b", {}, score === null ? "–" : String(score)), h("small", {}, "out of 100")));
}

/** One line per raw measurement: "Letter gap: 0.16× of the small-letter height (ideal 0.15× to 0.6×)". */
function measurementLines(featureId, measurements, model) {
  return (FEATURES[featureId] ? FEATURES[featureId].measurements : []).map((name) => {
    const ideal = idealRange(name, model);
    return h("span", { class: "meter-detail" },
      `${MEASUREMENTS[name].label}: ${formatMeasurement(name, measurements ? measurements[name] : null)}`,
      ideal ? ` (ideal ${ideal})` : "");
  });
}

/** Overall score ring plus one meter per feature, weakest first; unmeasured features last as
 *  "Not measured". Each meter is a button: onPick(featureId) highlights it on the photo.
 *  The weakest feature carries a "Focus" label so it never relies on color alone. */
export function scoreCard(result, { model = null, onPick = null, refs = {} } = {}) {
  const a = result.analysis;
  const scores = result.scores || {};
  const weakest = weakestFactor(scores);
  const measured = factorKeys(scores).sort((x, y) => scores[x] - scores[y]);
  const missing = FEATURE_IDS.filter((k) => !measured.includes(k));

  const meter = (key) => {
    const score = scores[key];
    const isMissing = typeof score !== "number";
    const isFocus = key === weakest;
    const fill = h("div", { class: "meter-fill" });
    if (!isMissing) requestAnimationFrame(() => requestAnimationFrame(() => { fill.style.width = `${score}%`; }));
    const el = h(onPick && !isMissing ? "button" : "div", {
      class: `meter${isFocus ? " focus" : ""}${isMissing ? " missing" : ""}`,
      type: onPick && !isMissing ? "button" : undefined,
      "aria-label": `${factorLabel(key)}: ${isMissing ? "not measured" : `${score} out of 100`}${isFocus ? ", your focus" : ""}`,
    },
      h("span", { class: "meter-name" }, factorLabel(key), isFocus ? h("span", { class: "focus-tag" }, "Focus") : null),
      h("div", { class: "meter-bar" }, fill),
      h("span", { class: "meter-value" }, isMissing ? "Not measured" : String(score)),
      h("span", { class: "meter-details" }, measurementLines(key, a.featureMeasurements, model)),
    );
    if (onPick && !isMissing) el.addEventListener("click", () => onPick(key));
    refs[key] = el;
    return el;
  };

  return h("div", { class: "score-card" },
    scoreRing(a.legibilityScore),
    h("div", {},
      h("div", { class: "score-verdict" }, a.scoreLabel || "Not enough to score"),
      h("div", { class: "score-sub" }, "Overall legibility score"),
      h("div", { class: "estimate-tag" }, "Experimental estimate"),
      weakest ? h("div", { class: "score-sub", style: "margin-top:6px" }, "Focus: ", h("b", {}, factorLabel(weakest))) : null,
    ),
    h("div", { class: "meters" },
      onPick && measured.length ? h("p", { class: "meters-hint" }, "Weakest first. Tap a feature to see it on your page.") : null,
      measured.map(meter), missing.map(meter)),
  );
}
