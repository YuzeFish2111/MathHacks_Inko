# Inko: a handwriting legibility estimator

Take a photo of your handwriting, or write on the screen, and Inko measures it like a mathematician
would: it finds every letter, takes nine measurements (size, proportions, baseline, slant, height
consistency, stroke contrast, stroke width, spacing, spacing consistency), turns them into eight
feature scores with explicit curves, and combines them into an experimental 0-100 legibility score.
Problem letters and gaps are marked on your photo, and Miggle, the in-app assistant, gives up to three
practice tips. Every number can be traced back to its formula in the app's "Show the maths" panel.

Built for the MathHacks hackathon (theme: mathematical modelling).

---

## Setup (about 5 minutes)

**You need:** Python 3.10 or newer (`python3 --version`) on macOS, Windows or Linux, and two terminal
windows. On Windows, type `py` wherever this page says `python3`.

### 1. Start the analysis backend (terminal 1)

```bash
cd backend
python3 -m pip install -r requirements.txt     # first time only (a few minutes; see the note on OCR below)
python3 -m uvicorn app.main:app --port 8000
```

Check it: <http://127.0.0.1:8000/api/health> should show `{"status":"ok","schemaVersion":"2.1"}`.
Interactive API docs are at <http://127.0.0.1:8000/docs>.

### 2. Start the Inko web app (terminal 2)

```bash
cd frontend
python3 run.py
```

The first run creates `frontend/.venv` and installs its packages (about a minute). It then prints:
- whether it can reach the backend from step 1;
- the address for this computer: **<http://localhost:5173>**;
- an address and QR code for phones on the same Wi-Fi.

### 3. Try it

1. Open <http://localhost:5173> and go to **Decoder**.
2. Tap **Try an example** for an instant result, or upload a photo, or choose **Write on screen**.
3. On the result, open **Show the maths** to see:
   - the score breakdown (each feature's score x weight);
   - a "What if?" simulator: drag any measurement and watch the score change;
   - a robust-statistics demo: drag a letter off the line and compare the Theil-Sen baseline (what the
     app uses) with an ordinary least-squares line.

**Optional demo account** with three weeks of progress history (run while both servers are up):

```bash
cd frontend
.venv/bin/python scripts/seed_demo.py          # Windows: .venv\Scripts\python scripts\seed_demo.py
```

Then sign in as `demo` / `inko-demo` and open **Progress**.

### Optional: on a phone

- **Same Wi-Fi:** scan the QR code printed by `run.py`. If it doesn't load, the network may block
  devices from seeing each other; connect the laptop to your phone's hotspot instead.
- **Anywhere, with an https link** (also lets you install Inko as an app): `brew install cloudflared`
  once, then run `python3 run.py --tunnel` and open the printed `trycloudflare.com` link.
  The laptop must stay on and awake while you use the link.

### Note on text recognition (OCR)

"What a computer read" uses EasyOCR, which runs locally (no API key) and downloads its model once on
first use. It is display-only: it never changes the score. If the download fails, the app still works
and shows "Text recognition isn't available". On macOS this usually means Python's certificates aren't
installed: run `open "/Applications/Python 3.x/Install Certificates.command"` (your version), then
restart the backend.

---

## Run the tests

```bash
cd backend  && python3 -m pytest -q             # 112 tests: pipeline, measurements, scoring, API
cd frontend && .venv/bin/python -m pytest -q server/tests   # web server: uploads, accounts, contract
```

The tests use synthetic images where the right answer is known exactly (a box drawn 40 px tall must
measure 40 px; a page tilted 6 degrees must be straightened to within 0.5 degrees), so they need no
photos and no network.

---

## How the score works (short version)

1. **Measure.** Nine measurements, each a ratio so it doesn't depend on camera resolution
   (for example, the median letter gap divided by the small-letter height).
2. **Be robust.** Baselines are fitted with **Theil-Sen regression** (the median of all pairwise slopes),
   and spreads use the **median absolute deviation** x 1.4826, so a few odd letters (descenders,
   a stray mark) can't dominate. Letter heights are only compared within their own height group
   (small letters with small letters, tall with tall), found from the natural break in each line's heights.
3. **Score.** Each measurement goes through a curve to a 0-1 score: a trapezoid when both too little and
   too much are bad, a straight decreasing line when less variation is better.
4. **Combine.** legibilityScore = 100 x the weighted mean of the available feature scores, rounded half up.
   A feature that can't be measured is left out and the other weights are rescaled; it is never counted
   as 0. The weights are equal (1/8) and the curve values are first guesses, which is why the score is
   labelled "Experimental estimate"; `validation/WEIGHT_FITTING_GUIDE.md` describes how to calibrate them
   against human ratings.

Every tunable number lives in one file: `backend/app/scoring_config.py`.

---

## Project layout

```
backend/            the analysis API (Python, FastAPI, OpenCV, NumPy, SciPy)
  app/
    main.py             endpoints, photo quality checks, overlays
    image_pipeline.py   page detection, cropping, lighting correction, deskew, ink mask, letters
    measurements.py     the nine measurements, height groups, Theil-Sen baseline
    scoring.py          curves -> feature scores -> legibility score
    scoring_config.py   every threshold, curve, weight and score band
    issues.py           which letters and gaps get marked on the photo
    advice.py           up to three tips, weakest feature first
    schemas.py          the response contract (Pydantic)
  tests/              backend tests
  GUIDE.md            full backend documentation (API, every module, the maths, troubleshooting)
frontend/           Inko, the web app (FastAPI server + plain HTML/CSS/JS, installable on phones)
  run.py              one-command start
  server/             uploads, HEIC/EXIF handling, accounts and history (SQLite), forwarding to the backend
  web/                the app the browser loads
  GUIDE.md            full web-app documentation
shared/             the API contract both halves follow, and example responses
validation/         plan and notebook for calibrating the score against human ratings
```

For depth, read `backend/GUIDE.md` (sections 5 and 7 explain every measurement and the scoring model)
and `frontend/GUIDE.md`.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Inko says it can't reach the scoring server | Start the backend (step 1) and leave that terminal open. |
| `Address already in use` | Another copy is running: close it, or use `--port 8001` (backend) / `python3 run.py --port 5174`. If you move the backend, set `ANALYSIS_API_URL` in `frontend/.env` (copy `.env.example`). |
| `pip install` fails on NumPy or OpenCV | Use Python 3.10-3.14 and upgrade pip: `python3 -m pip install --upgrade pip`. |
| "We couldn't separate the letters clearly" | Write at least one full sentence in print (separate letters), with small gaps between letters. |
| Photo results look off | Plain white paper, dark pen, even light with no shadows, phone held straight above the page. |

## Known limitations

- Joined-up cursive: letters that touch merge into one blob, so analysis needs printed handwriting.
- Latin-script handwriting only.
- The scoring curves and weights are not yet calibrated against human ratings.
