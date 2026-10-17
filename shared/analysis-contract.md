# Analysis Contract

Canonical API and variable glossary for the MathHacks Handwriting Legibility project.
Copied from the Canonical Naming Contract in the project plan. Use these names verbatim in
prompts, API payloads, shared types, fixtures and UI props.

`frontend/src/types/analysis.ts` and `backend/app/schemas.py` must both match this file
field-for-field. Example responses: `shared/fixtures/`.

## Naming rules

- camelCase for shared data and runtime identifiers, PascalCase for type/class names,
  UPPER_SNAKE_CASE for constants. Private helpers (e.g. snake_case Python functions) may
  follow local conventions but must map to this contract at the boundary.
- Include units in names: `Mm`, `Px`, `Deg`, `Pct`, `Cv`, `Ratio`.
- Do not use ambiguous shared names such as `s`, `scale`, `size`, `score`, `img` or `x` without context.
- `legibilityScore` is the final 0-100 score; `normalizedScore` is a feature's 0-1 value.
- Use `featureId` values from the fixed list; do not invent synonyms.
- `inkMask` always means ink foreground: true/1/255 is handwriting; false/0 is paper.
- Overlay coordinates always refer to the rectified image and use pixel units.
- Use `null` when a metric cannot be estimated. `0` is a real measurement.

## Image pipeline variables

| Name | Meaning |
|---|---|
| `originalImage` | Uploaded source image, unchanged |
| `grayscaleImage` | Grayscale source image |
| `backgroundEstimate` | Estimated paper illumination/background |
| `normalizedImage` | Shading-corrected grayscale image |
| `inkMask` | Binary image; foreground is handwriting ink |
| `rectifiedImage` | Cropped and perspective-corrected page |
| `cornerPointsPx` | Four page corners in originalImage pixels (top-left, top-right, bottom-right, bottom-left) |
| `deskewAngleDeg` | Applied rotation angle in degrees |
| `pageWidthMm`, `pageHeightMm` | User-provided physical paper dimensions |
| `pageWidthPx`, `pageHeightPx` | Rectified page dimensions in pixels |
| `scaleMmPerPxX`, `scaleMmPerPxY` | mm per pixel: pageWidthMm / pageWidthPx, etc. |
| `textLines` | Detected writing lines, ordered top-to-bottom |
| `letterComponents` | Candidate connected components; not guaranteed letters |
| `wordGaps` | Gaps classified as between words |
| `letterGaps` | Gaps classified as between adjacent letters |
| `qualityChecks` | Named image/input checks and their outcomes |

## Measurement and score variables

| Name | Meaning |
|---|---|
| `textSizeMm` | Median candidate component height, mm |
| `xHeightMm` | Estimated lowercase-body height, mm |
| `baselineVariationMm` | Std. deviation from fitted baseline, mm |
| `slantStdDeg` | Std. deviation of estimated slant, degrees |
| `strokeContrastRatio` | 90th / 10th percentile stroke width |
| `strokeWidthMedianMm` | Median stroke width, mm |
| `relativeLetterSpacing` | Median within-word letter gap / x-height; unitless |
| `letterSpacingCv` | CV of within-word letter gaps |
| `ocrConfidencePct` | How confidently a text-recognition model (EasyOCR) reads the writing, 0-100; null if OCR is unavailable or reads nothing |
| `recognizedText` | What the OCR model read (shown to the user); null if OCR is unavailable |
| `featureMeasurements` | Object containing the raw measurements above |
| `featureScores` | Map featureId -> 0-1 normalized score or null |
| `featureWeights` | Map featureId -> weight used (renormalized over available features) |
| `missingFeatureIds` | featureIds whose score is null |
| `legibilityScore` | Final weighted estimate, 0-100 or null |
| `humanLegibilityRating` | Mean blind human rating, 1-10; validation only |
| `readingAccuracyPct` | Optional transcription accuracy, 0-100 |

## Fixed feature IDs and their source measurements

| featureId | Source measurement | Curve |
|---|---|---|
| `textSize` | `textSizeMm` | sweet-spot |
| `xHeight` | `xHeightMm` | sweet-spot |
| `baselineConsistency` | `baselineVariationMm` | decreasing |
| `shapeConsistency` | `slantStdDeg` | decreasing |
| `strokeContrast` | `strokeContrastRatio` | decreasing |
| `strokeWeight` | `strokeWidthMedianMm` | sweet-spot |
| `letterSpacing` | `relativeLetterSpacing` | sweet-spot |
| `spacingConsistency` | `letterSpacingCv` | decreasing |
| `ocrReadability` | `ocrConfidencePct` | increasing |

OCR is optional: if EasyOCR isn't installed or its model can't load, `ocrReadability` is missing
(listed in `missingFeatureIds`), the other features share its weight, and a warning says so.

## Quality check IDs

`fileType`, `fileSize`, `decode`, `imageSize`, `blur`, `contrast`, `pageBounds`, `inkAmount`, `segmentation`

## Error codes (status `"needs_better_photo"`)

`INVALID_FILE_TYPE`, `FILE_TOO_LARGE`, `IMAGE_DECODE_FAILED`, `IMAGE_TOO_SMALL`,
`BLUR_TOO_HIGH`, `CONTRAST_TOO_LOW`, `PAGE_NOT_FOUND`, `NOT_ENOUGH_WRITING`,
`SEGMENTATION_UNCERTAIN`

## API

### `POST /api/analyze` (multipart/form-data)

| Field | Required | Type |
|---|---|---|
| `imageFile` | required | image file |
| `pageWidthMm` | required | number |
| `pageHeightMm` | required | number |
| `cornerPointsPx` | optional | JSON string `[[x,y],[x,y],[x,y],[x,y]]` in originalImage pixels, order top-left, top-right, bottom-right, bottom-left |

Rotating the photo (the preview screen's "Rotate 90°" button) happens in the browser before upload
(`frontend/src/utils/rotateImage.ts`). The backend only ever sees the uploaded, already-rotated image,
so `cornerPointsPx` and every overlay coordinate refer to that image. No extra field is sent.

### Response

- `schemaVersion`: `"1.3"` (1.2 added `ocrReadability`, `ocrConfidencePct` and `recognizedText`;
  1.3 removed `aspectRatioCv` and `solidityCv`, which mixed up letter identity with inconsistency,
  so `shapeConsistency` now comes from `slantStdDeg` alone. This differs from the original plan).
- `status`: `"complete"` or `"needs_better_photo"`.
- `error`: `null`, or `{ "code": string, "message": string }`.
- `qualityChecks` item: `{ "checkId": string, "passed": boolean, "message": string | null }`.
- Overlay line `kind`: `"baseline"` | `"xHeight"`. Gap `kind`: `"letter"` | `"word"`.
- `advice` item: `featureId`, `title`, `message`, `exercise`.
- `rectifiedImage`: data URL (PNG or JPEG) of the rectified page that overlays refer to.
- All overlay coordinates and dimensions are pixels in `"rectifiedImagePx"`.
- `issueFeatureIds` on a component or gap lists the features that box shows a problem with
  (empty list = no problem). Two kinds of mark:
  - **Element marks**, judged against the writer's own typical letter or gap:
    `baselineConsistency` (letter floats above or has sunk below its line; descenders are not marked),
    `shapeConsistency` (letter leans much more or less than the typical letter),
    `spacingConsistency` (letter gap much wider or narrower than the typical gap),
    `letterSpacing` (letter gap outside the ideal range, or letters joined into a cluster),
    `ocrReadability` (letter inside a word the OCR model read with low confidence).
  - **Whole-page marks**: `textSize`, `xHeight`, `strokeWeight`, `strokeContrast` are added to every
    letter when that feature scores at or below the threshold. Draw these as a page-level state
    (e.g. tint all letters when that feature is selected), not as individual problem boxes.
  - Word gaps are never marked. Thresholds live in `backend/app/scoring_config.py` (`ISSUE_*`).

Full examples (illustrative values only, not calibrated):

- `shared/fixtures/complete-response.json`
- `shared/fixtures/needs-better-photo-response.json`
