# Frontend guide: MathHacks Handwriting Legibility

> **Update: the frontend is now Inko** (plain HTML/CSS/JS, no React or Vite). Start it with
> `python3 run.py` in `frontend/`, next to the backend; see `README.md`. Steps 2-3 (Vite setup and
> proxy) and the React file names in steps 4-8 no longer apply. The ground rules, the results and
> retake screen requirements, and step 12 still do. The feature table in step 9 is from schema 1.4
> (mm); the backend now sends ratios (schema 2.1), and Inko reads the curves from
> `backend/app/scoring_config.py` instead of copying them.

Step-by-step instructions for building the React app. The backend is finished enough to build against:
`POST /api/analyze` takes a photo and returns a score, overlays and tips.

**Read first:** `shared/analysis-contract.md` (field names, units, error codes) and the "User flow"
section of `MathHacks-vibe-coding-plan.md`. If you use an AI assistant, give it the plan's
"Shared AI kickoff prompt" and these two files.

---

## Ground rules (please don't break these)

1. **Never rename a field.** Use the names in `src/types/analysis.ts` exactly. If you need a new field,
   change `shared/analysis-contract.md`, `src/types/analysis.ts` and `backend/app/schemas.py` together.
   A backend test fails if the TypeScript and Python field names drift apart.
2. **`null` means "couldn't be measured", and `0` is a real value.** Show "Not measured" for `null`, never 0.
3. **Overlay coordinates are pixels in `rectifiedImage`** (the straightened page the API sends back),
   not in the original photo. Scale them to whatever size you draw the image.
4. **Call the score an "experimental estimate".** It hasn't been checked against human ratings yet.
5. **Don't rely on colour alone.** Pair every colour with a label, icon or line style (the plan requires this).
6. **Design for a phone first** (about 390 px wide), then check desktop.

---

## Step 1: Run the backend on your computer

You need Python 3 and Node 18 or newer (`node --version`).

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Check it's running:
- http://127.0.0.1:8000/api/health should show `{"status":"ok","schemaVersion":"2.1"}`
- http://127.0.0.1:8000/docs lets you upload a photo by hand and see the real response

Keep this terminal open while you work on the frontend.

> If the response says "Text recognition isn't available", that's fine: OCR needs a one-time
> certificate fix (see `URGENT-TODO.md`). Everything else still works.

---

## Step 2: Create the React app (one person, once)

`frontend/src/` already contains some files (types, rotate button), so create the app **inside**
the existing folder:

```bash
cd frontend
npm create vite@latest . -- --template react-ts
```

When it says the folder isn't empty, choose **"Ignore files and continue"**. This keeps
`src/types/`, `src/utils/`, `src/hooks/` and `src/components/RotateButton.tsx`.
**Do not choose "Remove existing files"**: it deletes them (and this guide).

```bash
npm install
npm run dev
```

Open http://localhost:5173. You should see the Vite starter page. Commit this as one commit
("Set up Vite React app") before anyone builds features, so everyone starts from the same base.

---

## Step 3: Connect the dev server to the backend

Replace `frontend/vite.config.ts` with:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    // Forward /api/... to the Python backend, so the browser sees one address (no CORS problems,
    // and it also works from a phone on the same Wi-Fi)
    proxy: { "/api": "http://127.0.0.1:8000" },
    // Allow importing the shared example responses from ../shared/fixtures
    fs: { allow: [".."] },
  },
});
```

Restart `npm run dev`. Now `fetch("/api/health")` from the app reaches the backend.

---

## Step 4: The files you already have

| File | What it gives you |
|---|---|
| `src/types/analysis.ts` | TypeScript types for the request and the full response (`AnalysisResponse`) |
| `src/utils/rotateImage.ts` | `rotateImageFile()` turns the photo 90 degrees in the browser; `rotateCornerPointsClockwise()` moves corners to match |
| `src/hooks/useRotatablePhoto.ts` | Keeps the chosen photo, its rotation and a preview URL |
| `src/components/RotateButton.tsx` | The "Rotate 90°" button |
| `../shared/fixtures/complete-response.json` | A full example "complete" response |
| `../shared/fixtures/needs-better-photo-response.json` | A full example "retake your photo" response |

Suggested new folders and files (match these names so teammates can find things):

```
src/
  App.tsx                      screen switching (step 5)
  api/analyze.ts               the API call (step 6)
  constants/featureInfo.ts     labels, units, ideal ranges, curve parameters (step 9)
  mocks/mockResponses.ts       fixtures for building without the backend (step 5)
  pages/LandingPage.tsx
  pages/CapturePage.tsx
  pages/PreviewPage.tsx
  pages/ProcessingPage.tsx
  pages/ResultsPage.tsx
  pages/RetakePage.tsx         needs_better_photo result
  components/OverlayCanvas.tsx
  components/FeatureBars.tsx
  components/AdviceList.tsx
  utils/scoringModel.ts        the scoring maths in TypeScript, for the maths features (step 12)
  utils/robustStats.ts         median, least squares, Theil-Sen, CV (step 12)
  components/ScoreEquation.tsx       "Show the maths" score breakdown (step 12A)
  components/CurveChart.tsx          each feature's scoring curve with the user's point (step 12B)
  components/WhatIfSimulator.tsx     sliders that recompute the score live (step 12C)
  components/BaselineFitPanel.tsx    least squares vs Theil-Sen on the user's letters (step 12D)
  components/DistributionChart.tsx   histograms of gaps and letter heights (step 12E)
  pages/HowItWorksPage.tsx           the maths of each pipeline stage (step 12F)
```

---

## Step 5: Build the whole flow with mock data first

The plan says to finish the UI against example data before connecting the real API.

**5a. Mock responses** (`src/mocks/mockResponses.ts`):

```ts
import type { AnalysisResponse } from "../types/analysis";
import completeJson from "../../../shared/fixtures/complete-response.json";
import retakeJson from "../../../shared/fixtures/needs-better-photo-response.json";

// JSON imports lose exact string types ("complete" becomes string), hence the double cast
export const mockComplete = completeJson as unknown as AnalysisResponse;
export const mockNeedsBetterPhoto = retakeJson as unknown as AnalysisResponse;
```

If TypeScript complains about importing `.json`, add `"resolveJsonModule": true` under
`compilerOptions` in `tsconfig.app.json`.

The fixture's `rectifiedImage` is a placeholder (`data:image/jpeg;base64,...`), so use any sample
photo for the image while mocking. The overlay coordinates assume a 1200 x 1600 px image.

**5b. Screen switching** (`src/App.tsx`): keep it as one state value, no router needed:

```ts
type Screen = "landing" | "capture" | "preview" | "processing" | "results" | "retake";
```

Store in `App`: the current screen, the chosen `File`, the paper size (default 210 x 297 mm),
optional corners, and the latest `AnalysisResponse`. Pass them down as props.

Done when: you can click through landing, capture, preview, processing and results on a 390 px-wide
screen using only the mock data.

---

## Step 6: The API call (`src/api/analyze.ts`)

```ts
import type { AnalysisResponse, PointPx } from "../types/analysis";

export interface AnalyzeInput {
  imageFile: File;
  pageWidthMm: number;
  pageHeightMm: number;
  cornerPointsPx?: [PointPx, PointPx, PointPx, PointPx];
}

export async function analyzeHandwriting(input: AnalyzeInput): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append("imageFile", input.imageFile);
  form.append("pageWidthMm", String(input.pageWidthMm));
  form.append("pageHeightMm", String(input.pageHeightMm));
  if (input.cornerPointsPx) {
    form.append("cornerPointsPx", JSON.stringify(input.cornerPointsPx));   // must be a JSON string
  }

  let response: Response;
  try {
    response = await fetch("/api/analyze", { method: "POST", body: form });  // don't set Content-Type yourself
  } catch {
    throw new Error("Couldn't reach the server. Check your connection and try again.");
  }
  if (response.status === 422) {
    // Our own bug (bad form field), not the user's photo
    throw new Error("Something went wrong sending the photo. Please try again.");
  }
  if (!response.ok) {
    throw new Error(`The server had a problem (${response.status}). Please try again.`);
  }
  return (await response.json()) as AnalysisResponse;
}
```

After the call:
- `status === "complete"` -> results screen
- `status === "needs_better_photo"` -> retake screen (step 10)
- a thrown error -> show its message with a "Try again" button

The request takes a few seconds (longer the first time OCR runs), so always show the processing screen.

---

## Step 7: Landing and capture screens

**Landing:** one-line value proposition, an example result (use the mock), and an expandable
"How it works" section.

**Capture:**
- Photo input:
  ```tsx
  <input type="file" accept="image/*" capture="environment" onChange={...} />
  ```
  `capture="environment"` opens the back camera on phones; on desktop it opens a file picker.
  iPhones normally convert HEIC photos to JPEG for this input. The backend accepts JPEG, PNG and WebP.
- The capture checklist: copy the short version of `instructions.txt` (white paper, dark pen, write the
  sentence in print, whole page visible on a darker table, even light, no flash, hold the phone flat).
- Show the sentence to write: **The quick brown fox jumps over the lazy dog.**
- Paper size inputs in mm, defaulting to A4 (210 x 297). Validate that both are positive numbers.

---

## Step 8: Preview/crop screen

```tsx
const { photo, previewUrl, isRotating, rotationError, rotateClockwise } = useRotatablePhoto(chosenFile);

<img src={previewUrl ?? undefined} alt="Your handwriting photo" />
<RotateButton onRotate={rotateClockwise} isRotating={isRotating} errorMessage={rotationError} />
<button onClick={() => startAnalysis(photo)}>Analyse</button>
```

- **Always upload `photo`** (the rotated one), not the original file.
- **Corners are optional.** If you send none, the backend finds the page automatically, and if it
  can't, it uses the whole photo and adds a warning. Build that first (Option A in `URGENT-TODO.md`).
- If you add draggable corners:
  - Send them in **photo pixels**, not screen pixels:
    `xPx = xOnScreen * img.naturalWidth / img.clientWidth` (same for y with heights).
  - Order: **top-left, top-right, bottom-right, bottom-left**.
  - When the user rotates, clear the corners or move them with `rotateCornerPointsClockwise()`.
  - Handles at least 44 x 44 px so they're easy to drag with a finger.

---

## Step 9: Results screen

Show, top to bottom:

1. **Score and label**: `legibilityScore` (0-100) and `scoreLabel`, with the words
   "Experimental estimate".
2. **Annotated image**: `rectifiedImage` with the overlay canvas on top (below).
3. **Feature bars, weakest first**: sort `featureScores` from lowest to highest, skipping `null`s.
   Each bar shows the 0-100 score, the raw measurement with its unit, and the ideal range.
   Show features listed in `missingFeatureIds` as "Not measured" at the end.
4. **Tips**: `advice` (at most 3), each with `title`, `message` and `exercise`.
5. **What a computer read**: `recognizedText`, if it isn't `null`. It's for interest only and never
   affects the score, so don't show it as a score or a bar.
6. **Warnings**: `warnings` as small notes (e.g. page edges not found).
7. **Try again** button.

### Feature labels, units and ideal ranges (`src/constants/featureInfo.ts`)

The API doesn't send ideal ranges or curve parameters, so copy them from
`backend/app/scoring_config.py` (`SWEET_SPOT_CURVES`, `DECREASING_CURVES`, `FEATURE_WEIGHTS`). If someone
changes that file, update this table and the constants file together (or see step 12G, which removes
the need to copy).

| featureId | Label | Measurement | Unit | Ideal | Curve and parameters |
|---|---|---|---|---|---|
| `textSize` | Letter size | `textHeightCanvasRatio` | % of page height (x 100) | 1.0-2.5% | sweet-spot (0.005, 0.010, 0.025, 0.050) |
| `xHeight` | Small vs tall letters | `xHeightAscenderRatio` | % of tall letters' height (x 100) | 45-75% | sweet-spot (0.30, 0.45, 0.75, 0.95) |
| `baselineConsistency` | Staying on the line | `baselineVariationRatio` | % of small-letter height (x 100) | 10% or less | decreasing (0.10, 0.80) |
| `shapeConsistency` | Consistent slant and height | `slantStdDeg` and `letterHeightCv` (average of both scores) | degrees; % (x 100) | 2 or less; 5% or less | decreasing (2.0, 20.0); decreasing (0.05, 0.35) |
| `strokeContrast` | Even pen pressure | `strokeContrastRatio` | x (ratio) | 1.2 or less | decreasing (1.2, 4.0) |
| `strokeWeight` | Pen thickness | `strokeWidthRatio` | % of small-letter height (x 100) | 6-18% | sweet-spot (0.02, 0.06, 0.18, 0.35) |
| `letterSpacing` | Space between letters | `relativeLetterSpacing` | x letter height | 0.15-0.6 | sweet-spot (0.0, 0.15, 0.6, 1.2) |
| `spacingConsistency` | Even spacing | `letterSpacingCv` | % variation (x 100) | 15% or less | decreasing (0.15, 1.0) |

All eight features currently weigh 1/8. Sweet-spot (a, b, c, d): 0 outside a..d, rising a->b, 1 from
b to c, falling c->d. Decreasing (v0, v1): 1 at or below v0, falling in a straight line to 0 at v1.
`shapeConsistency` is the average of its two measurements' scores (just one if the other is null).
Since contract 2.0 all measurements are ratios (no mm); `textHeightCanvasRatio` is null when the page
edges weren't found. Height measures only compare letters of the same height group (see
`shared/analysis-contract.md`, "Height groups").

### Overlay canvas (`src/components/OverlayCanvas.tsx`)

- Put the `<img src={rectifiedImage}>` and a `<canvas>` in the same `position: relative` box, with the
  canvas `position: absolute; inset: 0`, sized to the image's displayed size.
- Scale every coordinate: `scale = displayedWidth / overlayData.imageWidthPx`. Redraw when the
  window is resized.
- Draw:
  - `lines` with `kind: "baseline"` as solid lines and `kind: "xHeight"` as dashed lines.
  - `components` as boxes around letters.
  - `gaps` with `kind: "letter"` as thin boxes between letters (skip `"word"` gaps unless toggled).
- **Toggles** (independent checkboxes, as the plan requires): *Spacing* (gaps), *Size* (letter boxes),
  *Baseline / x-height* (lines).
- **Problem highlighting:** each component and gap has `issueFeatureIds`. When a feature bar is
  tapped, highlight the boxes whose `issueFeatureIds` include that feature. Use a thicker outline
  plus an icon or label, not just a colour.
  - `textSize`, `xHeight`, `strokeWeight`, `strokeContrast` are **page-wide** marks that appear on
    nearly every letter. Show them as a light tint over all letters, not as many red boxes.

---

## Step 10: Retake screen (`status: "needs_better_photo"`)

- Show `error.message` prominently. It's already written for users (e.g. "The photo looks blurry...").
- Optionally list `qualityChecks` as a checklist (passed checks ticked, the failed one crossed).
- A "Take another photo" button goes back to capture with the paper size kept.

Error codes you can get (all in the contract): `INVALID_FILE_TYPE`, `FILE_TOO_LARGE`,
`IMAGE_DECODE_FAILED`, `IMAGE_TOO_SMALL`, `BLUR_TOO_HIGH`, `CONTRAST_TOO_LOW`, `PAGE_NOT_FOUND`,
`NOT_ENOUGH_WRITING`, `SEGMENTATION_UNCERTAIN`.

---

## Step 11: Processing screen

The backend does everything in one request, so it can't report progress. Show the plan's stages
(straighten page, separate ink from paper, measure writing, calculate score) as a list that ticks
through on a timer while waiting, and replace it with the result as soon as it arrives. Don't
show a fake percentage.

---

## Step 12: Make the maths visible

This is a maths-themed hackathon, so the results should show *how* the score was calculated, not just
the answer. Each idea below is a self-contained component; build them in order of value. Put them
behind a **"Show the maths"** toggle (or tab) on the results screen so the main view stays simple.

**Tools:** draw charts as plain **SVG** in React (small, no dependency, full control over labels), or use
a chart library if the team prefers. Render formulas with **KaTeX** (`npm install katex`, then
`katex.renderToString("...")`), so they look like real maths, not code.

**Ground rules for these features:**
- Every number shown must come from the response or from the documented model, never invented.
- Label everything that isn't validated as an experimental estimate.
- Keep text short: one formula plus one plain-English sentence per idea.

### Shared code: the scoring model in TypeScript (`src/utils/scoringModel.ts`)

Several features recompute scores in the browser. Port the backend's maths exactly:

```ts
import type { FeatureId } from "../types/analysis";

export type Curve =
  | { kind: "sweetSpot"; a: number; b: number; c: number; d: number }
  | { kind: "decreasing"; v0: number; v1: number };

/** Same as backend/app/scoring.py: a 0-1 score for one measurement, or null if unknown. */
export function scoreOnCurve(value: number | null, curve: Curve): number | null {
  if (value === null || !Number.isFinite(value)) return null;
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

/** Weighted mean over available features only, rescaled; rounded half up like the backend. */
export function legibilityScore(scores: Partial<Record<FeatureId, number | null>>,
                                weights: Record<FeatureId, number>): number | null {
  let weightedSum = 0, weightTotal = 0;
  for (const [featureId, score] of Object.entries(scores) as [FeatureId, number | null][]) {
    if (score === null || score === undefined) continue;
    weightedSum += weights[featureId] * score;
    weightTotal += weights[featureId];
  }
  return weightTotal > 0 ? Math.floor((100 * weightedSum) / weightTotal + 0.5) : null;
}
```

**Consistency check (do this first):** with the mock response, `legibilityScore(featureScores, weights)`
must equal the response's `legibilityScore`, and `scoreOnCurve(measurement, curve)` must equal each
`featureScores` value (to about 0.001); for `shapeConsistency`, average the scores of `slantStdDeg`
and `letterHeightCv`, skipping a null one. If not, the TypeScript copy has drifted from the backend.

### Build now: these need only the current API response

**12A. "Show the maths" score breakdown** (`ScoreEquation.tsx`). *Highest value; build first.*
- Show the formula with the user's own numbers:
  `score = 100 × (⅛·0.86 + ⅛·0.93 + ⅛·0.72 + …) = 78`, using `featureScores` and `featureWeights`.
- Under it, a **stacked bar** of each feature's contribution `100 × wₖ × fₖ`, so the segments add up
  to the score, plus the "lost points" `100 × wₖ × (1 − fₖ)` greyed out.
- If `missingFeatureIds` isn't empty, explain the rescaling in one line: "*Pen thickness couldn't be
  measured, so the other 7 features share its weight (1/7 each).*"

**12B. Scoring-curve chart per feature** (`CurveChart.tsx`).
- When a feature bar is tapped, show its curve (the trapezoid or the falling line) as an SVG graph:
  measurement on the x-axis, 0-1 score on the y-axis, the ideal zone shaded.
- Mark the user's measurement as a dot on the curve, with a dashed line down to the x-axis and across
  to the y-axis, labelled e.g. "your x-height: 3.1 mm → score 0.93".
- Show the piecewise formula next to it (KaTeX), e.g. for decreasing curves
  `f(m) = (v₁ − m) / (v₁ − v₀)`, clipped to [0, 1].

**12C. "What if" simulator** (`WhatIfSimulator.tsx`).
- One slider per measurement, starting at the user's value. Moving a slider recomputes that feature's
  score with `scoreOnCurve` and the total with `legibilityScore`, live.
- Show the **biggest lever**: for each feature, the points gained by reaching the ideal range,
  `100 × wₖ × (1 − fₖ)`, sorted. "*Fixing your letter spacing would add up to 4 points.*" This is the
  same order as the tips, so it explains *why* those tips were chosen.
- Label it clearly as a model simulation ("what the model would say"), not a prediction of a new photo.

**12D. Robust statistics demo: baseline fit** (`BaselineFitPanel.tsx`).
- From `overlayData.components`, take each box's bottom (`yPx + heightPx`) and centre
  (`xPx + widthPx / 2`) for one line. Fit two lines in the browser and draw both over the image:
  - **least squares** (the usual straight-line fit), and
  - **Theil-Sen** (the median of all pairwise slopes), which is what the backend uses.
- The i-dots, punctuation and descenders (g, j, p, q, y) are natural outliers. Show how least squares
  is pulled toward them while Theil-Sen isn't. Optional: let the user **drag one point** and watch the
  two lines react.
- Draw short vertical "residual" lines from each letter's bottom to the Theil-Sen baseline, with the
  formula for the spread, `1.4826 × median(|residual − median(residual)|)`.

```ts
// src/utils/robustStats.ts
export const median = (values: number[]) => {
  const sorted = [...values].sort((p, q) => p - q), mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};

/** Theil-Sen: slope = median of pairwise slopes; intercept = median(y) - slope * median(x).
 *  This is the same intercept rule as SciPy's theilslopes, which the backend uses. */
export function theilSen(xs: number[], ys: number[]) {
  const slopes: number[] = [];
  for (let i = 0; i < xs.length; i++)
    for (let j = i + 1; j < xs.length; j++)
      if (xs[j] !== xs[i]) slopes.push((ys[j] - ys[i]) / (xs[j] - xs[i]));
  const slope = median(slopes);
  return { slope, intercept: median(ys) - slope * median(xs) };
}

/** Ordinary least squares, for comparison. */
export function leastSquares(xs: number[], ys: number[]) {
  const meanX = xs.reduce((s, x) => s + x, 0) / xs.length, meanY = ys.reduce((s, y) => s + y, 0) / ys.length;
  let covariance = 0, variance = 0;
  xs.forEach((x, i) => { covariance += (x - meanX) * (ys[i] - meanY); variance += (x - meanX) ** 2; });
  const slope = variance ? covariance / variance : 0;
  return { slope, intercept: meanY - slope * meanX };
}
```

The browser's Theil-Sen line won't match the backend's baseline exactly: the response doesn't say which
boxes are letters, marks or clusters, and the backend uses letters only. Say so in a caption, or ask for
the component kind (see 12G).

**12E. Distributions: gaps and letter heights** (`DistributionChart.tsx`).
- **Gaps:** a histogram of `overlayData.gaps[].widthPx`, coloured and patterned by `kind` (letter vs word).
  Draw the median letter gap and the word-gap threshold (2.5 × the line's median gap) as vertical lines,
  so users see *how* the app decided which gaps are spaces between words.
- Show the coefficient of variation with its formula, `CV = σ / μ`, next to `letterSpacingCv`.
- **Letter heights:** a histogram of `components[].heightPx` with the median marked. The clusters of
  short (x-height) letters and tall (ascender) letters show why the app uses the median, not the mean.

**12F. "How it works" page** (`HowItWorksPage.tsx`, linked from the landing page).
One card per pipeline stage: a one-sentence explanation, the formula (KaTeX), and a small picture
(use the user's own image where possible, or the sample image):

| Card | Formula to show |
|---|---|
| Cropping the page | the page is found (Otsu threshold or Canny edges, convex hull, 4 corners) and cropped without warping, so letters keep their shape |
| Real-world scale | mm per pixel = paper width in mm ÷ page width in px |
| Removing shadows | I = R × L, so R = I ÷ L (the lighting L is estimated by a morphological closing) |
| Straightening | θ* = argmax over θ of Var(ink per row after rotating by θ) |
| Ink vs paper | a pixel is ink if it is more than C darker than its neighbourhood's weighted mean |
| Robust baseline | Theil-Sen slope = median of pairwise slopes; spread = 1.4826 × MAD |
| Slant | θ = atan(μ₁₁ / μ₀₂) from image moments |
| Stroke width | distance transform: width ≈ 2d − 1 at a stroke's centre |
| Scoring | trapezoid and linear curves, then a weighted mean over the measured features |
| Honest uncertainty | missing features are left out, not counted as 0; the score isn't validated yet |

The maths for every card is described in `backend/README.md` (sections 5 and 7) and in the docstrings
of `backend/app/image_pipeline.py` and `measurements.py`.

**Honesty panel.** Somewhere visible (results footer or the "How it works" page): "*This is an
experimental estimate. We plan to compare it with blind human ratings using rater agreement (ICC) and
rank correlation (Spearman).*" Replace with the real numbers once `validation/` has them.

### 12G. Needs backend data first (ask the backend person; contract change)

These need new fields or endpoints. Agree them first, then update `shared/analysis-contract.md`,
`schemas.py` and `analysis.ts` together (see "Ground rules"). Don't fake the data meanwhile.

| Feature | Backend addition needed | Why it's worth it |
|---|---|---|
| Curves and weights without copying | `GET /api/scoring-model` returning curves, weights, score bands and issue thresholds | removes the copied table in step 9, so the frontend can never drift from the backend |
| "How the computer sees it" stepper | optional image stages (lighting estimate, corrected page, ink mask) as data URLs, e.g. only when `includeDebugImages=true` | the most visual maths demo: each pipeline step on the user's own photo |
| Straightening chart | `deskewAngleDeg` plus the variance at each tried angle, and the ink-per-row profile | shows the optimisation itself: a curve with a clear peak at the chosen angle |
| Slant needles | each letter's slant angle (and `kind`: letter / mark / cluster) on `components` | draw a small slant line in every box, plus a histogram of slants |
| Flattening animation | the detected `cornerPointsPx` (or a `POST /api/detect-page` endpoint) | morph the photo into the flat page, showing the perspective correction |

Recommended order: `GET /api/scoring-model` first (it also fixes the copied-constants problem), then
debug images, then the deskew chart.

---

## Step 13: Test on a real phone

1. Start the backend as usual (step 1).
2. Start the frontend so other devices can reach it: `npm run dev -- --host`
3. On the phone (same Wi-Fi), open the "Network" address Vite prints, e.g. `http://192.168.1.20:5173`.
   The proxy from step 3 forwards API calls, so no backend change is needed.

Test: phone and desktop widths, a sideways photo plus the rotate button, a blurry photo, a blank page,
a slow connection (Chrome DevTools > Network > "Slow 4G"), and what happens when OCR is unavailable.

---

## Definition of done (from the plan)

- [ ] A user can finish landing -> capture -> preview -> processing -> results on a phone-sized screen.
- [ ] Loading, invalid-image (retake) and retry states all work.
- [ ] Overlays line up with the image at every screen size, and the three toggles work independently.
- [ ] Feature bars are weakest-first with raw value, unit and ideal range.
- [ ] Every result can be traced back to a mark on the image or a measurement.
- [ ] Nothing relies on colour alone, and the score is labelled as an experimental estimate.
- [ ] "Show the maths": the score breakdown (12A) and the curve charts (12B) work, and the TypeScript
      scoring model reproduces the response's scores (consistency check in step 12).
- [ ] The "How it works" page (12F) explains every pipeline stage with its formula.
- [ ] Every number in the maths features comes from the response or the documented model.

## Where to ask

- Field names, units or error codes: `shared/analysis-contract.md`
- What the backend does: `project-structure.txt` (file summaries) and `http://127.0.0.1:8000/docs`
- Something in the contract needs to change: agree it with the backend person first, then change the
  contract, `analysis.ts` and `schemas.py` together.
