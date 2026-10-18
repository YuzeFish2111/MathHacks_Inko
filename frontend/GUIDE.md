# Inko: the web app

Handwriting legibility coach. Upload a photo of your handwriting (or write on the screen), and
Miggle, the Miggle Assistant, shows an **experimental** legibility score, eight feature scores
with their raw measurements and ideal ranges, the problem spots marked on your straightened page,
the backend's tips, and printable practice worksheets.

Inko does no scoring itself. Every photo goes to the analysis backend in `../backend`
(`POST /api/analyze`, contract in `../shared/analysis-contract.md`), and Inko shows what comes back.

## Start everything (two terminals)

**1. The analysis backend** (from the project root):

```bash
cd backend
pip install -r requirements.txt     # first time only
uvicorn app.main:app --reload       # http://127.0.0.1:8000
```

**2. Inko** (from the project root):

```bash
cd frontend
python3 run.py
```

On Windows: `py run.py`. The first run creates `frontend/.venv` and installs `requirements.txt`
(about a minute). Every run prints:

- whether the analysis backend answers (and how to start it if not)
- the address for this computer: `http://localhost:5173`
- the address for phones on the same Wi-Fi, plus a QR code to scan

Phones only talk to Inko; Inko talks to the backend, so the backend doesn't need to be reachable
from the phone. If a phone can't connect: make sure it's on the same Wi-Fi, and click **Allow**
when your computer asks about incoming connections. School and event Wi-Fi often blocks devices
from seeing each other; turn on your phone's hotspot and connect the laptop to it instead.

The backend on another machine or port: set `ANALYSIS_API_URL` in `frontend/.env`
(copy `.env.example`).

### Install as an app (PWA)

- **Laptop:** open `http://localhost:5173` in Chrome or Edge and click Install (also in Settings).
  Safari on Mac: File, then Add to Dock.
- **Phone:** installing needs an https link. Run `python3 run.py --tunnel` (one-time setup:
  `brew install cloudflared`, no account needed) and open the printed `trycloudflare.com` link.
  Android Chrome shows an Install button; on iPhone tap Share, then Add to Home Screen
  (Inko shows this hint automatically).

### Demo account

With the backend running:

```bash
.venv/bin/python scripts/seed_demo.py
```

Then sign in as `demo` / `inko-demo` to show a Progress page with three weeks of improving scans
(made-up scores on the real analysis of the example photo). The "Try an example" button in the
Decoder works without signing in.

## How it fits together

```
browser (web/)  ──POST /analyze──▶  Inko server (server/)  ──POST /api/analyze──▶  analysis backend (../backend)
                ◀── { analysis, result_id, scores, ... } ──                ◀── AnalysisResponse (schema 2.1) ──
```

1. The browser checks the file type and size, shrinks big photos, and posts to Inko's `POST /analyze`.
2. The Inko server identifies the file from its bytes, converts HEIC to JPEG, applies EXIF rotation
   (so the backend always gets an upright JPEG), resizes to at most 2000 px, and checks for a tilted page.
   The "Try an example" photo is sent with `whole_page`, which Inko passes on as full-image
   `cornerPointsPx`, so the backend can judge letter size without page edges. Drawings are sent with
   `drawing`, passed on as `isDrawing`: the image is used whole, but a screen isn't a page, so letter
   size is "Not measured" and the score comes from the other seven features.
3. It forwards the JPEG to the backend's `POST /api/analyze` and validates the answer against the
   backend's own Pydantic contract (`backend/app/schemas.py`), so a drifted field fails loudly.
4. The answer is passed to the browser unchanged as `analysis`, wrapped with Inko's own fields:
   `result_id`, `created_at`, `photo_check`, `saved`, and for complete results `overall_score`
   (= `legibilityScore`) and `scores` (each `featureScores` value × 100, `null` when not measured).
5. Signed-in scans are saved to SQLite (passwords are salted scrypt hashes), including the
   straightened page the overlays refer to. Guests keep only their latest scores in the browser.

`status: "needs_better_photo"` is not an error: the Decoder shows the backend's `error.message`,
the `qualityChecks` list, and a "Take another photo" button. Nothing is saved.

`GET /api/scoring-model` serves the curves, weights and score bands straight from
`backend/app/scoring_config.py`, so the ideal ranges shown under each feature bar can't drift
from the backend. `GET /api/health` reports whether the backend answers and whether its
`schemaVersion` matches.

## "Show the maths" (results screen)

A card after the score (`web/js/components/mathpanel.js`, maths in `web/js/maths.js`) with three sections:

- **Score breakdown:** the weighted-average formula with the person's own numbers
  (`100 × (1/8 × 0.51 + …) = 78.4 → 78`), a stacked bar of points earned and lost per feature, and
  a note when a missing feature's weight is shared out.
- **What if…?:** a slider per measurement that recomputes the score live, plus the "biggest levers"
  (`100 × weight × (1 − score)`, the points each feature could add).
- **Robust statistics:** the letter bottoms of one line with a least-squares line and the Theil-Sen
  line the backend uses; drag a dot (or press "Drop the last letter below the line") to see least
  squares swing while Theil-Sen barely moves.

`maths.js` is a port of `backend/app/scoring.py`, using the curves and weights from
`GET /api/scoring-model`. It was checked against the Python backend on 300 random measurement sets
and 50 Theil-Sen fits (identical scores, labels and fits); keep the two in step if scoring changes.

## Rules carried over from the frontend guide

These come from the team's frontend notes and the contract, and the code follows them:

- **Never rename a contract field.** Inko reads `analysis.*` with the contract's names. Labels,
  units and the feature-to-worksheet mapping live in `web/js/features.js`.
- **`null` means "not measured", `0` is a real value.** Unmeasured features show "Not measured", last.
- **Overlay coordinates are `rectifiedImage` pixels.** The Decoder shows `rectifiedImage` (not the
  original photo) and draws the overlay as an SVG with the same viewBox, so it lines up at any size.
- **The score is labelled "Experimental estimate".**
- **No colour alone.** Baselines are solid lines and x-height lines dashed; problem boxes get a thick
  dashed outline plus a "!" marker; the focus feature has a "Focus" label; checks show ✓ / ✗ with words.
- **Phone first.** Checked at 390 px wide and on desktop.

## Editing team content

- Founder names, photos, and bios: `web/js/content.js` (`FOUNDERS`)
- Contact email, YouTube, Instagram links: `web/js/content.js` (`CONTACT`)
- Every status and error message: `web/js/messages.js` (server-side copies in `server/errors.py`)
- Feature labels and units: `web/js/features.js`
- Miggle's About Us bio: `web/js/content.js` (`MIGGLE`)
- Instagram posts to embed on Contact: `web/js/content.js` (`CONTACT.instagramPosts`); the newest YouTube video appears by itself

## Tests

```bash
.venv/bin/python -m pytest server/tests -q
```

The tests don't need the backend running: they use the example responses in `../shared/fixtures/`,
validated against the backend's contract. One test (`test_whole_page.py`) also runs the real backend
in-process when its packages are installed, and is skipped otherwise. The backend's own tests (`cd backend && python3 -m pytest`)
also check that `src/types/analysis.ts` still matches `schemas.py`, so keep that file.

## Folders

| Folder | What it holds |
| --- | --- |
| `server/` | Inko's FastAPI server: `/analyze` (forwards to the backend), HEIC/EXIF handling, tilt check, accounts, history |
| `web/` | The web app (plain HTML, CSS, JS modules, no build step), service worker, manifest, icons |
| `src/types/analysis.ts` | The contract types in TypeScript. Not used by Inko's plain JS, but the backend's tests check it |
| `scripts/` | Generators for the example photo and icons, demo account seeding |
| `designs/` | Canva mockups and logos |
| `data/` | Local SQLite database `inko.db` with accounts and saved scans (not committed) |
