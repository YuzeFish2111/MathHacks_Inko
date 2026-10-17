# MathHacks Handwriting Legibility — Vibe-Coding Plan (revised)

The full plan is the team's **HandwritingPlanv2** document. Paste its text here so every
contributor (and AI assistant) can read it from the repository.

The API and variable glossary are already in `shared/analysis-contract.md`.

MathHacks Handwriting Legibility — Vibe-Coding Plan (revised)
=============================================================
PROJECT OUTCOME
---------------
Build a phone-first web app that accepts a handwriting sample, checks whether the photo
is usable, estimates a small set of legibility features, and returns an understandable
score, image overlays, and a few actionable practice tips.
The score is an EXPERIMENTAL ESTIMATE, not a certified or universal measure of
handwriting quality. Start with transparent heuristics, then compare results with blind
human ratings before making strong claims.
RECOMMENDED IMPLEMENTATION
--------------------------
- Frontend: React + TypeScript, responsive single-page flow, HTML canvas for overlays.
- Backend: Python + FastAPI, with OpenCV for image processing and NumPy/SciPy as needed.
- Contract: one documented JSON request/response schema, kept in
shared/analysis-contract.md. Public field names below are canonical.
- Configuration: every threshold, ideal range, curve parameter, score band and weight
lives in backend/app/scoring_
config.py and nowhere else.
- Persistence: none for the first usable version. Keep the uploaded image in memory for
analysis; save previous scores locally in the browser only if the comparison feature
is implemented. Human-rating validation data is stored separately (see Validation).
This keeps the image math in Python while letting the browser render interactive
overlays. Build an end-to-end thin slice before attempting every metric.
USER FLOW
---------
landing -> capture -> preview/crop -> processing -> results
1. Landing: one-line value proposition, example result, expandable "How it works.
"
2. Capture: photo upload/camera input; a short capture checklist; paper size inputs
(default A4, 210 x 297 mm); and the standard sentence:
"The quick brown fox jumps over the lazy dog.
"
3. Preview/crop: show the selected image and detected page boundary. Allow manual
corner adjustment if automatic page detection fails. The user confirms before
analysis; manual corners are sent as cornerPointsPx.
4. Processing: show real pipeline stages: straighten page, separate ink from paper,
measure writing, calculate score.
5. Results: overall score and label, annotated writing image, feature bars and
measurements, then the two or three most useful tips. Include "Try again"; compare
with a previous attempt only after the basic result works.
Design narrow-screen-first. Use feature colors consistently, but pair color with labels,
line styles, or icons so overlays are not color-only.
BUILD SEQUENCE
--------------
0. Lock the contract before parallel coding
- Add this file to the repository root as MathHacks-vibe-coding-plan.md.
- Write shared/analysis-contract.md (API + variable glossary, copied from the
Canonical Naming Contract below).
- Create the shared types: frontend/src/types/analysis.ts and
backend/app/schemas.py (Pydantic). They must match field-for-field.
- Create fixtures: shared/fixtures/complete-response.json and
shared/fixtures/needs-better-photo-response.json.
- Create backend/app/scoring_
config.py with feature IDs, measurement-to-feature
mapping, curve parameters, weights, and score bands.
Done when: frontend and backend independently read the same fixtures and agree on
field names, units, null behavior, and coordinate system.
1. Build a complete UI with mock results (frontend)
- Implement the five user-flow states and responsive layout.
- Use a static sample image and a clearly labeled mock result from the fixtures.
- Implement overlay toggles and feature bars against mock coordinates.
- Include loading, invalid-image, and retry states.
Done when: a user can complete the flow on a phone-sized screen without a real
image-analysis backend.
2. Accept an image and establish page geometry (backend/app/image
_pipeline.py)
- Accept common phone image formats; validate type, size, dimensions, and decode
success.
- Collect real paper width and height in millimetres (pageWidthMm, pageHeightMm).
- Rectify/crop the page before measuring. Use cornerPointsPx when provided;
otherwise attempt automatic detection. If automatic detection is unreliable, keep
manual crop as the MVP path.
- If the image is resized, do it BEFORE thresholding and compute scaleMmPerPxX /
scaleMmPerPxY from the final rectified size in pixels.
- Add quality checks for blur, poor contrast, missing page bounds, and too little
writing. Return a specific retry message instead of a misleading score.
Done when: valid input produces a rectified image with known dimensions, and invalid
input produces a helpful needs
better
_
_photo response.
3. Implement preprocessing and segmentation (backend/app/image
_pipeline.py)
Run the pipeline in small testable functions:
1. Convert to grayscale.
2. Estimate uneven paper illumination and normalize it.
3. Threshold into the canonical ink mask (ink = 1/255, paper = 0).
4. Remove isolated noise and components below a configurable minimum area.
5. Deskew within a bounded range and crop empty margins.
6. Find text lines with horizontal projections.
7. Find connected components and candidate gaps within each line.
Do not label every connected component as a letter. Dots, punctuation, joined
letters, and multi-letter blobs need separate handling. Flag small components as
marks and suspiciously wide components as clusters; reduce confidence or suppress
metrics that depend on clean letter boundaries.
Done when: a small fixture set produces stable line/component boxes and the API
reports when segmentation is too uncertain.
4. Add measurements incrementally (backend/app/measurements.py)
Start with the most explainable and testable metrics:
1. Text size and x-height.
2. Baseline variation.
3. Relative letter spacing and spacing variation.
4. Shape consistency (aspect-ratio CV, solidity CV, slant standard deviation).
5. Stroke width and stroke contrast.
Use millimetres for physical lengths, pixels only for image coordinates, degrees for
slant, and unitless values for ratios/CVs. Keep unknown or unreliable measurements
as null; never silently substitute zero.
Done when: each metric has a unit test on a simple synthetic image and a visual
fixture showing the measurement on the source image.
5. Score and generate advice (backend/app/scoring.py, backend/app/advice.py)
- Normalize each feature to a 0-1 score; convert to 0-100 only for display.
- Use trapezoid (sweet-spot) curves for size, x-height, stroke weight, and relative
spacing. Use decreasing curves for consistency/contrast metrics.
- Map measurements to features with FEATURE
_
SOURCES in scoring_
config.py.
shapeConsistency is the mean of the available scores for aspectRatioCv,
solidityCv, and slantStdDeg.
- Start with documented equal weights (0.125 each).
- Calculate the weighted score only from available feature scores, dividing by the
sum of the weights actually used. List missing features in missingFeatureIds
rather than treating them as perfect or zero.
- Sort available feature scores weakest-first and generate at most three rule-based
tips, including the measured value where useful.
- Keep score bands configurable: 85+ Very legible, 70-84 Readable,
50-69 Some difficulty,
<50 Hard to read.
Done when: known fixture inputs produce deterministic measurements, scores, labels,
and advice; each tip identifies the measurement and direction to change.
6. Connect results, overlays, and validation
- Return the rectified image and overlay coordinates from the backend; draw overlays
in the browser over the rectified image, scaled to the canvas.
- Implement independent overlay toggles for spacing, size, and baseline/x-height.
- Show feature bars weakest-first, with raw measurement, unit, and ideal range.
- Test on phone and desktop widths, varied lighting, pen thicknesses, slanted pages,
joined writing, punctuation, and multi-line samples.
- Run the validation and weight-fitting procedure below.
Done when: a user can trace each result back to an image mark or measurement, and
the demo can explain where the model is reliable and where it is not.
VALIDATION AND WEIGHT FITTING
-----------------------------
Data (validation/):
- Collect 30-60 samples with consent: validation/samples/ (images) and
validation/ratings.csv (one row per sample per rater).
- At least three people rate each sample 1-10 WITHOUT seeing the model score.
Optionally record transcription accuracy (readingAccuracyPct).
- Photograph about five sheets three times each under different conditions to test
measurement stability.
- Hold out about one third of samples as a test set; do not use it until the end.
Weight regression (backend/app/fit
_
weights.py):
- Target: y = 100 * (humanLegibilityRating - 1) / 9.
- Use only samples where all eight feature scores are available.
- Fit y ~ b0 + sum(bk * fk) with bk >= 0 (non-negative least squares), with a ridge
penalty pulling coefficients toward equal values. Choose the penalty strength by
leave-one-out cross-validation.
- Store wk = bk / sum(bj) in FEATURE
_
WEIGHTS in scoring_
config.py. Keep b0 and sum(bj)
as a separate calibration that maps legibilityScore onto the human rating scale.
- Check feature correlations/VIF, bootstrap the weights for confidence intervals, and
keep fitted weights only if they beat equal weights under cross-validation.
- Curve parameters stay fixed during weight fitting.
Reporting:
- Inter-rater reliability (ICC) as the practical ceiling.
- Spearman correlation between legibilityScore and the mean human rating on the test
set, with a bootstrap 95% confidence interval and the sample size n.
CANONICAL NAMING CONTRACT
-------------------------
Use these names verbatim in prompts, API payloads, shared types, fixtures, and UI props.
Use camelCase for shared data and runtime identifiers, PascalCase for type/class names,
and UPPER
SNAKE
_
_
CASE for constants. Private language-specific helper names (for example
snake
_
case Python functions) may follow local conventions, but must map to this
contract at the boundary.
Naming rules
- Include units in names: Mm, Px, Deg, Pct, Cv, Ratio.
- Do not use ambiguous shared names such as s, scale, size, score, img, or x without
context.
- legibilityScore is the final 0-100 score; normalizedScore is a feature's 0-1 value.
- Use featureId values from the fixed list; do not invent synonyms.
- inkMask always means ink foreground: true/1/255 is handwriting; false/0 is paper.
- Overlay coordinates always refer to the rectified image and use pixel units.
- Use null when a metric cannot be estimated. 0 is a real measurement.
Image pipeline variables
originalImage Uploaded source image, unchanged
grayscaleImage Grayscale source image
backgroundEstimate Estimated paper illumination/background
normalizedImage Shading-corrected grayscale image
inkMask Binary image; foreground is handwriting ink
rectifiedImage Cropped and perspective-corrected page
cornerPointsPx Four page corners in originalImage pixels
(top-left, top-right, bottom-right, bottom-left)
deskewAngleDeg Applied rotation angle in degrees
pageWidthMm, pageHeightMm User-provided physical paper dimensions
pageWidthPx, pageHeightPx Rectified page dimensions in pixels
scaleMmPerPxX/Y mm per pixel: pageWidthMm / pageWidthPx, etc.
textLines Detected writing lines, ordered top-to-bottom
letterComponents Candidate connected components; not guaranteed letters
wordGaps Gaps classified as between words
letterGaps Gaps classified as between adjacent letters
qualityChecks Named image/input checks and their outcomes
Measurement and score variables
textSizeMm Median candidate component height, mm
xHeightMm Estimated lowercase-body height, mm
baselineVariationMm Std. deviation from fitted baseline, mm
aspectRatioCv CV of component width/height
solidityCv CV of component solidity
slantStdDeg Std. deviation of estimated slant, degrees
strokeContrastRatio 90th / 10th percentile stroke width
strokeWidthMedianMm Median stroke width, mm
relativeLetterSpacing Median within-word letter gap / x-height; unitless
letterSpacingCv CV of within-word letter gaps
featureMeasurements Object containing the raw measurements above
featureScores Map featureId -> 0-1 normalized score or null
featureWeights Map featureId -> weight used (renormalized over
available features)
missingFeatureIds featureIds whose score is null
legibilityScore Final weighted estimate, 0-100 or null
humanLegibilityRating Mean blind human rating, 1-10; validation only
readingAccuracyPct Optional transcription accuracy, 0-100
Fixed feature IDs and their source measurements
textSize <- textSizeMm (sweet-spot curve)
xHeight <- xHeightMm (sweet-spot curve)
baselineConsistency <- baselineVariationMm (decreasing curve)
shapeConsistency <- mean of aspectRatioCv, solidityCv, slantStdDeg
(decreasing curves)
strokeContrast <- strokeContrastRatio (decreasing curve)
strokeWeight <- strokeWidthMedianMm (sweet-spot curve)
letterSpacing <- relativeLetterSpacing (sweet-spot curve)
spacingConsistency <- letterSpacingCv (decreasing curve)
Quality check IDs
fileType, fileSize, decode, imageSize, blur, contrast, pageBounds, inkAmount,
segmentation
Error codes (status "needs
better
_
_photo")
INVALID
FILE
TYPE, FILE
TOO
LARGE, IMAGE
DECODE
_
_
_
_
_
_
IMAGE
TOO
SMALL,
_
_
BLUR
TOO
HIGH, CONTRAST
TOO
LOW, PAGE
NOT
_
_
_
_
_
_
NOT
ENOUGH
WRITING,
_
_
SEGMENTATION
UNCERTAIN
FAILED,
FOUND,
_
API
---
POST /api/analyze (multipart/form-data)
imageFile required image file
pageWidthMm required number
pageHeightMm required number
cornerPointsPx optional JSON string: [[x,y],[x,y],[x,y],[x,y]] in originalImage
pixels, order top-left, top-right, bottom-right,
bottom-left
Response: the TypeScript interface (frontend/src/types/analysis.ts) and the Pydantic
schema (backend/app/schemas.py) must both match the shape below.
Allowed status values: "complete"
"needs
better
,
_
_photo"
.
error: null, or { "code": string,
"message": string }.
qualityChecks item: { "checkId": string,
"passed": boolean,
"message": string | null }.
Overlay line kind: "baseline" | "xHeight"
. Gap kind: "letter" | "word"
.
advice item: featureId, title, message, exercise.
rectifiedImage: data URL (PNG or JPEG) of the rectified page that overlays refer to.
All overlay coordinates and dimensions are pixels in "rectifiedImagePx"
.
Example: complete (illustrative fixture values only, not calibrated)
{
"schemaVersion": "1.1"
,
"status": "complete"
,
"error": null,
"legibilityScore": 78,
"scoreLabel": "Readable"
,
"rectifiedImage": "data:image/jpeg;base64,...
"
,
"featureMeasurements": {
"textSizeMm": 6.2,
"xHeightMm": 3.1,
"baselineVariationMm": 0.8,
"aspectRatioCv": 0.24,
"solidityCv": 0.19,
"slantStdDeg": 5.4,
"strokeContrastRatio": 1.8,
"strokeWidthMedianMm": 0.42,
"relativeLetterSpacing": 0.31,
"letterSpacingCv": 0.38
},
"featureScores": {
"textSize": 0.86,
"xHeight": 0.93,
"baselineConsistency": 0.72,
"shapeConsistency": 0.81,
"strokeContrast": 0.78,
"strokeWeight": 0.84,
"letterSpacing": 0.68,
"spacingConsistency": 0.61
},
"featureWeights": {
"textSize": 0.125,
"xHeight": 0.125,
"baselineConsistency": 0.125,
"shapeConsistency": 0.125,
"strokeContrast": 0.125,
"strokeWeight": 0.125,
"letterSpacing": 0.125,
"spacingConsistency": 0.125
},
"missingFeatureIds": [],
"warnings": [],
"qualityChecks": [
{ "checkId": "blur"
,
"passed": true,
"message": null }
],
"overlayData": {
"coordinateSpace": "rectifiedImagePx"
,
"imageWidthPx": 1200,
"imageHeightPx": 1600,
"lines": [
{ "lineId": "line-1"
"kind": "baseline"
,
,
"x1Px": 100,
"y1Px": 430,
"x2Px": 1080,
"y2Px": 438 }
],
"components": [
{ "componentId": "component-1"
,
"xPx": 120,
"yPx": 390,
"widthPx": 28,
"issueFeatureIds": [] }
"lineId": "line-1"
,
"heightPx": 40,
],
"gaps": [
{ "gapId": "gap-1"
"lineId": "line-1"
,
,
"xPx": 148,
"yPx": 410,
"widthPx": 12,
"issueFeatureIds": ["letterSpacing"] }
"kind": "letter"
,
"heightPx": 4,
]
},
"advice": [
{
"featureId": "spacingConsistency"
,
"title": "Make letter gaps more even"
,
"message": "Your letter gaps vary by 38% (coefficient of variation 0.38).
"
,
"exercise": "Practice keeping a similar pencil-width gap between letters.
"
}
]
}
Example: needs
better
_
_photo
{
"schemaVersion": "1.1"
,
"status": "needs
better
_
_photo"
,
"error": {
"code": "BLUR
TOO
HIGH"
,
_
_
"message": "The photo looks blurry. Try holding your phone steady and retaking it.
"
},
"legibilityScore": null,
"scoreLabel": null,
"rectifiedImage": null,
"featureMeasurements": null,
"featureScores": null,
"featureWeights": null,
"missingFeatureIds": [],
"warnings": [],
"qualityChecks": [
{ "checkId": "blur"
,
"passed": false,
"message": "The photo looks blurry.
" }
],
"overlayData": null,
"advice": []
}
PROJECT LAYOUT
--------------
MathHacks-vibe-coding-plan.md this plan
backend/
app/
init
__
__
.py
main.py FastAPI app and POST /api/analyze
schemas.py Pydantic request/response models
scoring_
config.py feature IDs, FEATURE
_
SOURCES, curves, weights, bands
image
_pipeline.py validation, rectification, ink mask, lines, components
measurements.py the ten featureMeasurements
scoring.py curves, feature scores, legibilityScore, scoreLabel
advice.py weakest-first rule-based tips
fit
_
weights.py regression of weights against human ratings
tests/
test
test
_
image
_pipeline.py
measurements.py_
test
test
test
_
_
scoring.py
advice.py
api.py
_
requirements.txt numpy, opencv-python-headless, scipy, fastapi,
python-multipart, pydantic, pytest
frontend/
src/
components/
pages/
api/ API client (analyze request)
types/
analysis.ts TypeScript response interface
shared/
analysis-contract.md
fixtures/
complete-response.json
needs-better-photo-response.json
tests/
sample-images/ hard cases collected during testing
validation/
samples/ consented validation images (not public)
ratings.csv sampleId, raterId, rating, readingAccuracyPct
analysis.ipynb ICC, correlation, bootstrap, regression results
SHARED AI KICKOFF PROMPT
------------------------
You are contributing to the MathHacks Handwriting Legibility project. Read
MathHacks-vibe-coding-plan.md and shared/analysis-contract.md before changing code.
Preserve the canonical camelCase names, feature IDs, units, ink-mask polarity, and
rectified-image coordinate system defined there. Do not rename shared fields or create
alternate aliases. Keep all thresholds and weights in backend/app/scoring_
config.py.
Keep unknown measurements null, not zero. Make the smallest change for the assigned
milestone, add or update tests, and report files changed, checks run, and any
assumptions. Do not claim the legibility score is validated unless human-rating results
support that claim.
SOURCE BRIEF
------------
This plan is based on the "Project Plan" for the Catherine, Ayden, Sophie, and April
MathHacks project. The brief defines the image-processing approach, intended screens,
measurements, scoring, and human-rating validation. Its assumptions about connected
components and heuristic ideal ranges should be tested rather than treated as
established facts.