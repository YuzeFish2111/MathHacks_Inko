# Frontend guide: MathHacks Handwriting Legibility

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
- http://127.0.0.1:8000/api/health should show `{"status":"ok","schemaVersion":"1.3"}`
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
  constants/featureInfo.ts     labels, units, ideal ranges (step 9)
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
5. **What a computer read**: `recognizedText`, if it isn't `null`.
6. **Warnings**: `warnings` as small notes (e.g. page edges not found).
7. **Try again** button.

### Feature labels, units and ideal ranges (`src/constants/featureInfo.ts`)

The API doesn't send ideal ranges, so copy them from `backend/app/scoring_config.py`. If someone
changes that file, update this table and the constants file together.

| featureId | Label | Measurement | Unit | Ideal |
|---|---|---|---|---|
| `textSize` | Letter size | `textSizeMm` | mm | 3.0-7.0 |
| `xHeight` | Small-letter height | `xHeightMm` | mm | 2.0-4.5 |
| `baselineConsistency` | Staying on the line | `baselineVariationMm` | mm | 0.3 or less |
| `shapeConsistency` | Consistent slant | `slantStdDeg` | degrees | 2 or less |
| `strokeContrast` | Even pen pressure | `strokeContrastRatio` | x (ratio) | 1.2 or less |
| `strokeWeight` | Pen thickness | `strokeWidthMedianMm` | mm | 0.3-0.8 |
| `letterSpacing` | Space between letters | `relativeLetterSpacing` | x letter height | 0.15-0.6 |
| `spacingConsistency` | Even spacing | `letterSpacingCv` | % variation (x 100) | 15% or less |
| `ocrReadability` | Computer readability | `ocrConfidencePct` | % | 85% or more |

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

## Step 12: Test on a real phone

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

## Where to ask

- Field names, units or error codes: `shared/analysis-contract.md`
- What the backend does: `project-structure.txt` (file summaries) and `http://127.0.0.1:8000/docs`
- Something in the contract needs to change: agree it with the backend person first, then change the
  contract, `analysis.ts` and `schemas.py` together.
