# Urgent to-do (before the next step)

Snapshot: 2026-10-17. The backend works end to end (95 tests passing), but **only on computer-generated
images**. These items block a trustworthy demo. Do the "Today" items first; most can run in parallel.

Put your name next to an item when you take it.

## Today: blockers

| # | Task | Why it's urgent | Owner |
|---|------|-----------------|-------|
| 1 | **Take 5-10 real photos that follow `instructions.txt`** (whole page visible, darker table, even light, the pangram in print). Save them in `tests/sample-images/`. | Every real photo so far (`data/`) breaks the instructions, so all their scores are meaningless (35-48, "Hard to read"). Nothing can be tuned without proper photos. | |
| 2 | **Run those photos through the API** (`http://127.0.0.1:8000/docs`) and write down the score, warnings and any wrong overlay marks. | The thresholds in `backend/app/scoring_config.py` are first guesses. This shows which ones are wrong. | |
| 3 | **Fix the Mac certificate problem**: open Applications > Python 3.14 > *Install Certificates.command*, then restart the server. | Without it the OCR model can't download, so `ocrReadability` is always missing. OCR has only ever been tested with a fake. | |
| 4 | **Set up the React app** in `frontend/` (step 2 of `frontend/README.md`). | There is no runnable frontend yet, so there's nothing to demo. | |
| 5 | **Decide on the page-corner preview** (see below). | The preview/crop screen needs it, and it changes what the frontend builds. | |

### Decision needed for item 5: how does the preview screen get page corners?
- **Option A (simplest, works now):** the frontend shows the photo with a rotate button and lets the user
  optionally drag four corners. If they don't, the backend finds the page itself.
- **Option B (nicer):** add a backend endpoint `POST /api/detect-page` that returns the detected corners,
  so the preview screen can show them before analysis. This is a small contract addition
  (`shared/analysis-contract.md`) plus a little backend code.

Recommendation: build Option A first, add B if time allows.

## Before the demo

| # | Task | Why | Owner |
|---|------|-----|-------|
| 6 | **Check the photos in `data/` are the team's own handwriting**, or remove them. They are public on GitHub. Anything from outside the team needs consent and belongs in `validation/samples/` (git-ignored). Deleting a file doesn't remove it from git history. | Privacy: the plan requires consent for samples. | |
| 7 | **Start collecting validation ratings**: 30-60 samples, each rated 1-10 by 3+ people who haven't seen the app's score (`validation/ratings.csv`). | Takes the longest, because it needs other people's time. Without it we can't say how well the score matches human judgement. | |
| 8 | **Feature-bar ideal ranges for the frontend**: the API doesn't send them. Copy them into the frontend (see `frontend/README.md`, step 9) or add them to the API response. | The results screen must show "your value vs. the ideal range". | |
| 9 | **Re-check scores once OCR runs for real**: EasyOCR may "read" messy writing correctly because the pangram is famous, which makes its confidence too high. Compare a messy and a neat sample. | Decides whether OCR deserves its 1/9 weight. | |
| 10 | **After `pip install`, check OpenCV still works** (`python3 -c "import cv2"`). `easyocr` can install a second OpenCV (`opencv-python`) that clashes with `opencv-python-headless`; if so, `pip uninstall opencv-python`. | A clash breaks the whole backend. | |

## Later (nice to have)
- Automatic 90/180/270-degree orientation detection in the backend (the frontend rotate button covers it for now).
- `backend/app/fit_weights.py`: fit the feature weights to the human ratings (needs item 7).
- Letter-level features: x-height consistency, comparison with an ideal example.
