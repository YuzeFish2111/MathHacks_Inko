import { h } from "../ui.js";
import { FEATURE_IDS, featureLabel, formatMeasurement, MEASUREMENTS } from "../features.js";
import {
  featureScoresFrom, labelFor, leastSquares, legibilityFrom, robustSpread, scoreOnCurve,
  standardDeviation, theilSen,
} from "../maths.js";

// "Show the maths": how the score was built, a what-if simulator, and a robust-statistics demo.
// Every number comes from the backend's answer (result.analysis) or its scoring model
// (GET /api/scoring-model); nothing is invented. Each part is a <details> section.

const SVG = "http://www.w3.org/2000/svg";

function svg(tag, attrs = {}, text) {
  const node = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, String(v));
  if (text !== undefined) node.textContent = text;
  return node;
}

const round = (n, digits) => Number(n.toFixed(digits));

/** "1/8" for weights that are a simple fraction, otherwise a decimal. */
function weightText(weight) {
  const n = Math.round(1 / weight);
  return Math.abs(1 / n - weight) < 1e-6 ? `1/${n}` : String(round(weight, 3));
}

function section(title, summaryNote, body, open = false) {
  return h("details", { class: "math-section", open },
    h("summary", {}, h("b", {}, title), h("span", { class: "math-summary-note" }, summaryNote)),
    h("div", { class: "math-body" }, body));
}

// ---------- 1. Score breakdown ----------

function scoreBreakdown(a) {
  const scores = a.featureScores, weights = a.featureWeights;
  const used = FEATURE_IDS.filter((k) => scores[k] !== null && weights[k] !== undefined);
  const exact = 100 * used.reduce((sum, k) => sum + weights[k] * scores[k], 0);

  const terms = used.map((k, i) => h("span", { class: "eq-term" },
    i ? " + " : "", h("span", { class: "eq-weight" }, weightText(weights[k])), " × ",
    h("span", { class: "eq-score", title: featureLabel(k) }, round(scores[k], 2).toFixed(2))));
  const equation = h("p", { class: "equation", "aria-label": `Score equals 100 times the weighted average of ${used.length} feature scores, ${round(exact, 1)}, rounded to ${a.legibilityScore}` },
    "score = 100 × (", terms, ") = ", h("b", {}, String(round(exact, 1))), " → ", h("b", {}, String(a.legibilityScore)));

  // One slot per feature, as wide as its weight; the filled part is the points it earned.
  const slots = used.map((k, i) => {
    const earned = 100 * weights[k] * scores[k], possible = 100 * weights[k];
    return h("div", { class: `stack-slot${i % 2 ? " alt" : ""}`, style: `flex-basis:${possible}%`,
      title: `${featureLabel(k)}: ${round(earned, 1)} of ${round(possible, 1)} points` },
      h("div", { class: "stack-earned", style: `width:${100 * scores[k]}%` }));
  });
  const rows = used
    .map((k) => ({ k, earned: 100 * weights[k] * scores[k], lost: 100 * weights[k] * (1 - scores[k]) }))
    .sort((p, q) => q.lost - p.lost)
    .map(({ k, earned, lost }) => h("li", {},
      h("b", {}, featureLabel(k)), `: ${round(earned, 1)} points earned`,
      lost >= 0.05 ? h("span", { class: "lost" }, `, ${round(lost, 1)} lost`) : " (full marks)"));

  const missing = a.missingFeatureIds || [];
  const missingNote = missing.length
    ? h("p", { class: "math-note" },
      `${missing.map(featureLabel).join(", ")} couldn’t be measured, so ${missing.length === 1 ? "it is" : "they are"} left out: `,
      `the other ${used.length} features share the weight (${weightText(1 / used.length)} each), instead of counting it as 0 or as perfect.`)
    : null;

  return h("div", {},
    h("p", {}, "Your score is a weighted average of the feature scores (each from 0 to 1), times 100, rounded to a whole number."),
    equation,
    h("div", { class: "stack-bar", role: "img", "aria-label": "Points earned per feature; the striped part of each slot is points lost" }, slots),
    h("p", { class: "math-caption" }, "Each slot is one feature, as wide as its weight. Filled = points earned, striped = points lost."),
    h("ul", { class: "math-list" }, rows),
    missingNote);
}

// ---------- 2. What-if simulator ----------

/** Slider range for a measurement: a bit beyond its curve, always including the person's value. */
function sliderRange(curve, value) {
  let lo, hi;
  if (curve.kind === "decreasing") { lo = 0; hi = curve.v1 * 1.25; }
  else { lo = Math.max(0, curve.a - (curve.b - curve.a)); hi = curve.d + (curve.d - curve.c); }
  return { lo: Math.min(lo, value), hi: Math.max(hi, value * 1.1) };
}

function whatIf(a, model) {
  const original = { ...a.featureMeasurements };
  const names = Object.values(model.featureSources).flat()
    .filter((name, i, all) => all.indexOf(name) === i && original[name] !== null && original[name] !== undefined && model.curves[name]);
  const sim = { ...original };

  const total = h("b", {}), label = h("span", {}), delta = h("span", { class: "whatif-delta" });
  const rowReadouts = {};
  const sliders = {};

  function update() {
    const result = legibilityFrom(featureScoresFrom(sim, model), model.featureWeights);
    total.textContent = result.score === null ? "–" : String(result.score);
    label.textContent = labelFor(result.score, model) || "";
    const diff = (result.score ?? 0) - (a.legibilityScore ?? 0);
    delta.textContent = diff ? ` (${diff > 0 ? "+" : ""}${diff} from your real score)` : " (same as your real score)";
    for (const name of names) {
      const s = scoreOnCurve(sim[name], model.curves[name]);
      rowReadouts[name].textContent = `${formatMeasurement(name, sim[name])}  →  ${Math.round(100 * s)}/100`;
    }
  }

  const rows = names.map((name) => {
    const { lo, hi } = sliderRange(model.curves[name], original[name]);
    const input = h("input", { type: "range", min: lo, max: hi, step: (hi - lo) / 400, value: original[name],
      "aria-label": `${MEASUREMENTS[name] ? MEASUREMENTS[name].label : name}, what-if value` });
    input.addEventListener("input", () => { sim[name] = Number(input.value); update(); });
    sliders[name] = input;
    rowReadouts[name] = h("span", { class: "whatif-readout" });
    return h("label", { class: "whatif-row" },
      h("span", { class: "whatif-name" }, MEASUREMENTS[name] ? MEASUREMENTS[name].label : name), input, rowReadouts[name]);
  });

  const reset = h("button", { class: "btn btn-small btn-soft", type: "button" }, "Back to my real values");
  reset.addEventListener("click", () => {
    for (const name of names) { sim[name] = original[name]; sliders[name].value = original[name]; }
    update();
  });

  // Biggest levers: points each feature could add if it reached full marks, 100 x w x (1 - f).
  const levers = FEATURE_IDS
    .filter((k) => a.featureScores[k] !== null && a.featureWeights[k] !== undefined)
    .map((k) => ({ k, gain: 100 * a.featureWeights[k] * (1 - a.featureScores[k]) }))
    .filter(({ gain }) => gain >= 0.5)
    .sort((p, q) => q.gain - p.gain)
    .slice(0, 3);

  update();
  return h("div", {},
    h("p", {}, "Move a slider to see what the model would say if that measurement were different. ",
      "This is the scoring model’s answer, not a prediction for a new photo."),
    h("p", { class: "whatif-total", role: "status" }, "Simulated score: ", total, " ", label, delta),
    h("div", { class: "whatif-rows" }, rows),
    reset,
    levers.length
      ? h("div", { class: "levers" },
        h("p", {}, h("b", {}, "Biggest levers"), " — points each feature could add at full marks, ",
          h("span", { class: "equation inline" }, "100 × weight × (1 − score)"), ":"),
        h("ol", { class: "math-list" }, levers.map(({ k, gain }) => h("li", {}, h("b", {}, featureLabel(k)), `: up to +${round(gain, 1)} points`))))
      : h("p", { class: "math-note" }, "Every feature is already at or near full marks."));
}

// ---------- 3. Robust statistics: fitting the baseline ----------

function robustDemo(a) {
  const overlay = a.overlayData;
  const byLine = {};
  for (const c of overlay.components) (byLine[c.lineId] ||= []).push(c);
  const lineIds = Object.keys(byLine).filter((id) => byLine[id].length >= 3);
  if (!lineIds.length) return h("p", { class: "math-note" }, "There aren’t enough letters on one line to fit a baseline.");

  let lineId = lineIds.reduce((best, id) => (byLine[id].length > byLine[best].length ? id : best), lineIds[0]);
  let original = [], points = [];
  // Taller plot on phones, where it is only ~330 px wide
  const W = 640, H = typeof window !== "undefined" && window.innerWidth < 600 ? 420 : 260, PAD = 24;
  const plot = svg("svg", { class: "robust-plot", viewBox: `0 0 ${W} ${H}`, role: "img" });
  const readout = h("div", { class: "robust-readout", role: "status" });
  let toScreen = null, toDataY = null, dragging = -1;

  function loadLine() {
    original = byLine[lineId].map((c) => ({ x: c.xPx + c.widthPx / 2, y: c.yPx + c.heightPx }));
    points = original.map((p) => ({ ...p }));
    const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const heights = byLine[lineId].map((c) => c.heightPx).sort((p, q) => p - q);
    const span = Math.max(heights[Math.floor(heights.length / 2)] * 2, Math.max(...ys) - Math.min(...ys) + 20);
    const midY = (Math.max(...ys) + Math.min(...ys)) / 2;
    const yTop = midY - span / 2;
    // Data -> screen: x across the plot, y downward like the page
    toScreen = (x, y) => [PAD + (x - minX) / Math.max(1, maxX - minX) * (W - 2 * PAD), PAD + (y - yTop) / span * (H - 2 * PAD)];
    toDataY = (sy) => yTop + (sy - PAD) / (H - 2 * PAD) * span;
  }

  function lineEnds(fit) {
    const xs = points.map((p) => p.x), x1 = Math.min(...xs), x2 = Math.max(...xs);
    return [...toScreen(x1, fit.slope * x1 + fit.intercept), ...toScreen(x2, fit.slope * x2 + fit.intercept)];
  }

  /** Viewbox units per screen pixel, so dots keep a sensible on-screen size at any width. */
  function unitsPerPx() {
    const width = plot.getBoundingClientRect ? plot.getBoundingClientRect().width : 0;
    return width ? W / width : 1;
  }

  function draw() {
    const xs = points.map((p) => p.x), ys = points.map((p) => p.y);
    const u = unitsPerPx();
    const robust = theilSen(xs, ys), plain = leastSquares(xs, ys);
    const residuals = points.map((p) => p.y - (robust.slope * p.x + robust.intercept));
    plot.replaceChildren();
    plot.setAttribute("aria-label", `Letter bottoms on one line, with the Theil-Sen baseline (solid) and the least-squares line (dashed)`);
    const screen = points.map((p) => [...toScreen(p.x, p.y), toScreen(p.x, robust.slope * p.x + robust.intercept)[1]]);
    screen.forEach(([sx, sy, fy]) => plot.append(svg("line", { class: "rp-residual", x1: sx, y1: sy, x2: sx, y2: fy })));
    const [r1x, r1y, r2x, r2y] = lineEnds(robust), [l1x, l1y, l2x, l2y] = lineEnds(plain);
    plot.append(
      svg("line", { class: "rp-least", x1: l1x, y1: l1y, x2: l2x, y2: l2y }),
      svg("line", { class: "rp-robust", x1: r1x, y1: r1y, x2: r2x, y2: r2y }),
      svg("text", { class: "rp-label", x: W - PAD, y: 16, "text-anchor": "end" }, "lower on the page ↓"));
    // Dots last, so they sit on top of the lines; each gets a ~40 px invisible touch target
    screen.forEach(([sx, sy], i) => plot.append(
      svg("circle", { class: `rp-point${points[i].y !== original[i].y ? " moved" : ""}`, cx: sx, cy: sy, r: 6 * u }),
      svg("circle", { class: "rp-hit", cx: sx, cy: sy, r: 20 * u, "data-index": i })));
    const angle = (fit) => round(Math.atan(fit.slope) * 180 / Math.PI, 2);
    readout.replaceChildren(
      h("p", {}, h("b", {}, "Theil-Sen (solid, what the app uses): "), `tilt ${angle(robust)}°, spread ${round(robustSpread(residuals), 1)} px `,
        h("span", { class: "equation inline" }, "= 1.4826 × median|r − median(r)|")),
      h("p", {}, h("b", {}, "Least squares (dashed, the usual best fit): "), `tilt ${angle(plain)}°; plain standard deviation of the same residuals ${round(standardDeviation(residuals), 1)} px`));
  }

  plot.addEventListener("pointerdown", (e) => {
    if (!e.target.hasAttribute || !e.target.hasAttribute("data-index")) return;
    e.preventDefault();
    dragging = Number(e.target.getAttribute("data-index"));
    plot.setPointerCapture(e.pointerId);
  });
  plot.addEventListener("pointermove", (e) => {
    if (dragging < 0) return;
    const pt = plot.createSVGPoint(); pt.x = e.clientX; pt.y = e.clientY;
    const local = pt.matrixTransform(plot.getScreenCTM().inverse());
    points[dragging].y = toDataY(Math.min(H - 4, Math.max(4, local.y)));
    draw();
  });
  const stop = () => { dragging = -1; };
  plot.addEventListener("pointerup", stop);
  plot.addEventListener("pointercancel", stop);

  const outlier = h("button", { class: "btn btn-small", type: "button" }, "Drop the last letter below the line");
  outlier.addEventListener("click", () => {
    const i = points.length - 1;   // an end point has the most leverage on least squares
    const heights = byLine[lineId].map((c) => c.heightPx).sort((p, q) => p - q);
    points[i].y = original[i].y + heights[Math.floor(heights.length / 2)] * 0.8;
    draw();
  });
  const reset = h("button", { class: "btn btn-small btn-soft", type: "button" }, "Reset");
  reset.addEventListener("click", () => { points = original.map((p) => ({ ...p })); draw(); });

  const picker = lineIds.length > 1
    ? h("div", { class: "row robust-lines", role: "group", "aria-label": "Which line of writing" },
      lineIds.map((id, n) => {
        const b = h("button", { class: "btn btn-small btn-soft", type: "button", "aria-pressed": String(id === lineId) }, `Line ${n + 1}`);
        b.addEventListener("click", () => {
          lineId = id; loadLine(); draw();
          picker.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
        });
        return b;
      }))
    : null;

  loadLine();
  draw();
  // Redraw once the plot has its real size (dot sizes depend on it) and whenever it resizes
  let drawnWidth = 0;
  if (typeof ResizeObserver !== "undefined") new ResizeObserver(([entry]) => {
    const width = Math.round(entry.contentRect.width);
    if (width && width !== drawnWidth && dragging < 0) { drawnWidth = width; draw(); }
  }).observe(plot);
  return h("div", {},
    h("p", {}, "Each dot is the bottom of one ink blob on a line of your writing. Two ways to fit a line through them: ",
      h("b", {}, "least squares"), " (the usual best fit, pulled toward every point) and ",
      h("b", {}, "Theil-Sen"), ", the median of the slopes between every pair of dots, which barely moves when a few dots are odd. ",
      "Drag a dot up or down (or use the button) and watch which line follows it."),
    picker,
    h("div", { class: "robust-plot-wrap" }, plot),
    h("div", { class: "row" }, outlier, reset),
    readout,
    h("p", { class: "math-caption" }, "Dots include i-dots, punctuation and descenders (g, j, p, q, y), which is exactly why the app uses robust statistics. ",
      "The app’s own baseline uses letters only, so it can differ slightly from this one."));
}

// ---------- the card ----------

/** "Show the maths" card for a complete result. model = GET /api/scoring-model (may be null). */
export function mathPanel(result, model) {
  const a = result.analysis;
  if (!a || a.status !== "complete" || !a.featureScores) return null;
  return h("div", { class: "math-panel" },
    h("h3", {}, "Show the maths"),
    h("p", { class: "math-intro" }, "How your experimental score is built, and the statistics behind it."),
    section("Score breakdown", "the formula with your numbers", scoreBreakdown(a), true),
    model
      ? section("What if…?", "change a measurement, see the score", whatIf(a, model))
      : h("p", { class: "math-note" }, "The what-if simulator needs the scoring model, which couldn’t be loaded."),
    section("Robust statistics", "why one odd letter can’t fool the baseline", robustDemo(a)));
}
