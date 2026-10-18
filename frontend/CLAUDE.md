# Inko (frontend/) — Project Notes

2-day hackathon project. Runs on localhost (no cloud hosting needed).

## What the app does
User uploads a photo of their handwriting (dark pen on white paper) or writes directly on the screen.
The analysis backend (`../backend`) straightens the page, measures eight features and returns an
experimental 0-100 legibility score, feature scores, overlay marks and up to three tips. Inko shows
them, offers practice worksheets, and (with an account) tracks progress over time.

## Architecture
- **Analysis backend** (`../backend`, owned by the backend team): `POST /api/analyze`, contract in
  `../shared/analysis-contract.md` (schema 2.1). Inko never scores anything itself.
- **Inko server** (`server/`, FastAPI, port 5173): serves `web/`, accounts, history (SQLite in
  `data/`), and `POST /analyze`, which prepares the photo (HEIC, EXIF,
  resize), forwards it to the backend, validates the answer with `backend/app/schemas.py`, and
  returns `{ analysis: <AnalysisResponse>, result_id, created_at, photo_check, saved, overall_score, scores }`.
- **Web app** (`web/`): plain HTML/CSS/JS modules, no build step. Reads contract fields by their exact
  names from `result.analysis`.

## Rules (from `IMPORTANT_READS.md` and the contract)
- Never rename a contract field; changes go through `shared/analysis-contract.md`,
  `src/types/analysis.ts` and `backend/app/schemas.py` together.
- `null` = "Not measured", `0` is a real value.
- Overlay coordinates are `rectifiedImage` pixels: always draw over `analysis.rectifiedImage`.
- Label the score "Experimental estimate". Never rely on colour alone. Phone first (390 px).
- Ideal ranges come from `GET /api/scoring-model` (reads `backend/app/scoring_config.py`); don't copy them.

## Photo input (important)
- Upload button: `accept="image/*"` with `capture="environment"` so phones can open the rear camera, AND allow choosing from the photo library.
- EXIF rotation and HEIC are handled in `server/imaging.py` before forwarding, so the backend always gets an upright JPEG.
- Drawings and the bundled example are sent with `whole_page` so the backend is told the whole image is the page
  (otherwise it can't judge letter size without page edges).
- On-screen writing: HTML canvas → export as an image → same `/analyze` endpoint.

## PWA
- `web/manifest.json`, `web/sw.js` (bump `CACHE` when app files change shape), icons in `web/icons/`.
- PWA install on phones requires https: `python3 run.py --tunnel`.
