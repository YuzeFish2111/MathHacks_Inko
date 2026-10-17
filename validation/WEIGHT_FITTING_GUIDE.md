# Guide: fitting the feature weights to human ratings

**Goal:** replace the placeholder equal weights (1/9 each, in `backend/app/scoring_config.py`) with
weights learned from how people actually rate handwriting, and measure how well the app's score
agrees with people. This follows the "Validation and weight fitting" section of the project plan.

**You need:** 30-60 consented handwriting samples, at least 3 raters, the backend installed
(`pip install -r backend/requirements.txt`), and about a day spread over a week (most of it is
waiting for ratings).

**The honest expectation:** with 30-60 samples and 9 features, fitted weights are noisy. It's quite
likely that equal weights do just as well, and that is a valid, reportable result. The point is to
*test* the weights, not to force a change.

---

## Step 1: Collect the samples

1. Get **written consent** from each writer (what it's for, who sees it, that it won't be public).
2. Each writer copies *The quick brown fox jumps over the lazy dog.* on plain white paper, following
   `instructions.txt`.
3. Photograph each sheet the same way (whole page visible, darker table, even light).
4. Save the photos in `validation/samples/` named by an anonymous ID: `S01.jpg`, `S02.jpg`, ...
   This folder is git-ignored, so the photos never reach GitHub. Keep the ID-to-person list
   somewhere private, not in the repo.
5. Aim for **variety**: neat and messy, small and large, pen and pencil. If every sample is neat,
   there is nothing to learn from.

**Stability check (plan requirement):** photograph about 5 of the sheets **3 times each** under
different conditions (window light, room light, slightly different angle). Save them as
`S01-b.jpg`, `S01-c.jpg` and so on. They are only used in step 4b, never for fitting.

---

## Step 2: Collect blind ratings

1. Each rater scores **every** sample from **1 (unreadable) to 10 (perfectly legible)**.
2. Raters must **not** see the app's score, each other's ratings, or who wrote what.
3. Show the samples in a **different random order** for each rater (a shuffled slideshow or printouts).
4. Give every rater the same one-line instruction, e.g. *"How easy is this to read? 1 = can't read it,
   10 = effortless."*
5. Optional: ask raters to type out what they read. Comparing it with the real sentence gives
   `readingAccuracyPct` (100 x correct characters / total characters).

Record everything in `validation/ratings.csv`, one row per sample per rater:

```csv
sampleId,raterId,rating,readingAccuracyPct
S01,R1,7,100
S01,R2,8,
S01,R3,6,97.7
S02,R1,3,81.4
```

---

## Step 3: Split off a test set, once, before looking at any scores

Hold out about a third of the samples. **Don't use them for anything until step 11.** If you look at
them while choosing weights, the final result will be optimistic.

```python
# validation/make_split.py  (run once, then commit split.csv)
import csv, random
sampleIds = sorted({row["sampleId"] for row in csv.DictReader(open("validation/ratings.csv"))})
random.Random(2026).shuffle(sampleIds)                 # fixed seed: same split every time
testCount = round(len(sampleIds) / 3)
with open("validation/split.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["sampleId", "set"])
    for i, sampleId in enumerate(sampleIds):
        writer.writerow([sampleId, "test" if i < testCount else "train"])
```

---

## Step 4: Get the app's feature scores for every sample

Run from the `backend/` folder. This calls the real API in-process, with OCR on if it's set up.

```python
# backend/scripts/score_samples.py
import csv, json, pathlib
from fastapi.testclient import TestClient
from app.main import app
from app.scoring_config import FEATURE_IDS

client = TestClient(app)
rows, skipped = [], []
for photo in sorted(pathlib.Path("../validation/samples").glob("*.*")):
    with open(photo, "rb") as f:
        body = client.post("/api/analyze", data={"pageWidthMm": "210", "pageHeightMm": "297"},
                           files={"imageFile": (photo.name, f.read(), "image/jpeg")}).json()
    if body["status"] != "complete":
        skipped.append((photo.stem, body["error"]["code"]))
        continue
    rows.append({"sampleId": photo.stem, "legibilityScore": body["legibilityScore"],
                 **{featureId: body["featureScores"][featureId] for featureId in FEATURE_IDS}})

with open("../validation/features.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=["sampleId", "legibilityScore", *FEATURE_IDS])
    writer.writeheader()
    writer.writerows(rows)
print("scored", len(rows), "| needs better photo:", skipped)
```

- Re-photograph any sample that comes back as "needs better photo", rather than dropping it silently.
- **Use the same settings for every sample.** If OCR works for some runs and not others, the
  `ocrReadability` column will be half empty. Either get OCR working first or set
  `OCR_ENABLED = False` and fit 8 features.
- The plan says to fit only on samples where **all** feature scores are present. Write down how many
  were left out, and why.

### Step 4b: Stability check

For the sheets photographed 3 times, compare the 3 `legibilityScore`s and each feature score. Report
the typical spread (standard deviation). A feature that jumps around between photos of the *same*
sheet can't be trusted, whatever weight it gets.

---

## Step 5: Shared helper code

Put these functions in `backend/app/fit_weights.py` (currently a placeholder). They were tested
on simulated data: a very large penalty returns exactly equal weights, and every coefficient stays
at 0 or above.

```python
import numpy as np
from scipy.optimize import lsq_linear
from scipy.stats import spearmanr


def fit_weights(F, y, ridgeStrength):
    """Fit y ~ b0 + F @ b with every b >= 0, plus a penalty pulling the b's toward a common value.

    F: samples x features (feature scores 0-1). y: human target 0-100 (step 7).
    ridgeStrength = 0 means no pull; very large means equal weights.
    Returns (b0, b).
    """
    n, k = F.shape
    A = np.hstack([np.ones((n, 1)), F])                        # column 0 is the intercept b0
    # Penalty rows: sqrt(lambda) * (b - mean of b); the intercept isn't penalised
    centering = np.eye(k) - np.ones((k, k)) / k
    P = np.hstack([np.zeros((k, 1)), np.sqrt(ridgeStrength) * centering])
    lower = np.r_[-np.inf, np.zeros(k)]                        # b0 free, every b >= 0
    result = lsq_linear(np.vstack([A, P]), np.r_[y, np.zeros(k)], bounds=(lower, np.inf))
    return result.x[0], result.x[1:]


def loocv_rmse(F, y, ridgeStrength):
    """Leave-one-out error: fit without each sample in turn, predict it, return the RMS error."""
    errors = []
    for i in range(len(y)):
        keep = np.arange(len(y)) != i
        b0, b = fit_weights(F[keep], y[keep], ridgeStrength)
        errors.append(y[i] - (b0 + F[i] @ b))
    return float(np.sqrt(np.mean(np.square(errors))))


def icc2(ratings):
    """ICC(2,1) and ICC(2,k) (two-way random effects, absolute agreement).

    ratings: samples x raters array with no gaps (every rater rated every sample).
    """
    n, k = ratings.shape
    grand = ratings.mean()
    rowMeans, colMeans = ratings.mean(axis=1), ratings.mean(axis=0)
    msr = k * np.sum((rowMeans - grand) ** 2) / (n - 1)
    msc = n * np.sum((colMeans - grand) ** 2) / (k - 1)
    sse = np.sum((ratings - rowMeans[:, None] - colMeans[None, :] + grand) ** 2)
    mse = sse / ((n - 1) * (k - 1))
    single = (msr - mse) / (msr + (k - 1) * mse + k * (msc - mse) / n)
    average = (msr - mse) / (msr + (msc - mse) / n)
    return single, average
```

---

## Step 6: Check that the raters agree (ICC)

Build a samples x raters table from `ratings.csv` and run `icc2(table)`.

- **ICC(2,1)**: how much a single rater agrees with the others.
- **ICC(2,k)**: how reliable the **average** of your k raters is. This is the **practical ceiling**:
  the app can't be expected to agree with the average rating better than the raters agree with each other.

Common reading (Koo and Li, 2016): below 0.5 poor, 0.5-0.75 moderate, 0.75-0.9 good, above 0.9 excellent.
If ICC(2,k) is poor, fix the rating instructions and re-rate before fitting anything.

---

## Step 7: Build the target

For each sample: `humanLegibilityRating` = the mean of its ratings (1-10). Put it on the app's scale:

```
y = 100 * (humanLegibilityRating - 1) / 9      # 1 -> 0, 10 -> 100
```

`F` is the matrix of the 9 feature scores (0-1) from `features.csv`, rows in the same sample order as `y`.

---

## Step 8: Check the features before fitting

```python
import numpy as np
correlations = np.corrcoef(F_train, rowvar=False)              # 9 x 9 table

def vif(F):
    """Variance inflation factor per feature: 1 / (1 - R^2 of that feature predicted from the others)."""
    values = []
    for j in range(F.shape[1]):
        others = np.delete(F, j, axis=1)
        X = np.hstack([np.ones((len(F), 1)), others])
        fitted = X @ np.linalg.lstsq(X, F[:, j], rcond=None)[0]
        r2 = 1 - np.sum((F[:, j] - fitted) ** 2) / np.sum((F[:, j] - F[:, j].mean()) ** 2)
        values.append(1 / (1 - r2) if r2 < 1 else float("inf"))
    return values
```

- `textSize` and `xHeight` are likely to be strongly correlated. That's expected (they measure similar
  things), but it means their individual weights are unreliable and only their sum is meaningful.
- VIF above 5 = notable overlap; above 10 = their separate weights can't be trusted.
- A feature that is the same for nearly every sample (no spread) can't get a meaningful weight.

---

## Step 9: Fit, choosing the penalty by leave-one-out (training set only)

```python
grid = [0, 0.1, 0.3, 1, 3, 10, 30, 100, 1000]
errors = {lam: loocv_rmse(F_train, y_train, lam) for lam in grid}
bestLambda = min(errors, key=errors.get)
b0, b = fit_weights(F_train, y_train, bestLambda)
fittedWeights = b / b.sum()                                     # w_k = b_k / sum(b)
```

Keep two numbers as a **calibration** (the plan asks for this):
- `b0` (intercept) and `S = b.sum()`. With the new weights, `legibilityScore = 100 * sum(w_k * f_k)`,
  so the predicted human score is `b0 + S * legibilityScore / 100` (then back to 1-10 with `1 + 9 * y / 100`).

**Curve parameters stay fixed** while fitting weights. Don't tune curves and weights at the same time.

---

## Step 10: Keep the fitted weights only if they beat equal weights

Equal weights are the same model with a huge penalty, so compare them the same way:

```python
equalError = loocv_rmse(F_train, y_train, 1e6)                  # equal weights, still fits b0 and the scale
print(f"fitted: {errors[bestLambda]:.2f}   equal: {equalError:.2f}")
```

Keep the fitted weights only if their leave-one-out error is **clearly** lower, say by at least 5%.
Otherwise keep equal weights and report that the data didn't support a change.

**How sure are the weights? Bootstrap them:**

```python
rng = np.random.default_rng(2026)
draws = []
for _ in range(1000):
    pick = rng.integers(0, len(y_train), len(y_train))          # resample samples with replacement
    _, bootB = fit_weights(F_train[pick], y_train[pick], bestLambda)
    draws.append(bootB / bootB.sum() if bootB.sum() > 0 else np.full(len(bootB), np.nan))
low, high = np.nanpercentile(draws, [2.5, 97.5], axis=0)        # 95% interval per feature
```

Wide intervals (e.g. 0.02-0.30) mean that weight is mostly guesswork. Report them.

---

## Step 11: Final evaluation on the test set (once)

Only now open the test samples. Compute each test sample's score with the chosen weights and compare
it with the mean human rating:

```python
from scipy.stats import spearmanr
appScores = 100 * F_test @ chosenWeights
rho = spearmanr(appScores, humanMean_test).correlation

rng = np.random.default_rng(2026)
bootRhos = []
for _ in range(2000):
    pick = rng.integers(0, len(appScores), len(appScores))
    bootRhos.append(spearmanr(appScores[pick], humanMean_test[pick]).correlation)
low, high = np.nanpercentile(bootRhos, [2.5, 97.5])
print(f"Spearman rho = {rho:.2f} (95% CI {low:.2f} to {high:.2f}), n = {len(appScores)}")
```

Spearman correlation asks "does the app *rank* samples the same way people do?" (1 = identical order,
0 = unrelated). Compare it with the ICC from step 6: the app getting close to the raters' own agreement
is a strong result. With about 15-20 test samples the confidence interval will be wide; say so.

---

## Step 12: Put the result into the app

1. In `backend/app/scoring_config.py`, replace the equal weights:
   ```python
   FEATURE_WEIGHTS = {"textSize": 0.14, "xHeight": 0.09, ...}   # fitted on n=..., see validation report
   ```
   They must cover every featureId and sum to 1.
2. Save `b0` and `S` as named constants (e.g. `HUMAN_CALIBRATION_INTERCEPT`, `HUMAN_CALIBRATION_SLOPE`)
   with a comment. The API doesn't use them yet.
3. Run the tests: `cd backend && python3 -m pytest`. One test (`test_missing_features_are_excluded...`
   in `test_scoring.py`) assumes equal weights and will need its expected numbers updated.
4. Only now may the app or slides say the score was **checked against human ratings**, quoting the
   numbers from step 11.

---

## What to report (template)

> We collected **n = __** samples rated by **__** raters (1-10, blind to the app's score).
> Rater agreement: ICC(2,1) = __, ICC(2,k) = __.
> Stability: the same sheet photographed 3 times varied by __ points (SD) on average.
> Fitted weights [did / did not] beat equal weights in leave-one-out validation (RMSE __ vs __),
> so we use [fitted / equal] weights. Largest weights: __ (95% CI __).
> On __ held-out test samples, the app's score ranked samples like the human average with
> Spearman rho = __ (95% CI __ to __).

## Common mistakes
- Looking at the test set before step 11.
- Raters seeing the app's score, each other's ratings, or knowing whose writing it is.
- Mixing runs with and without OCR, or photographed under different conditions.
- Tuning the curves and the weights at the same time.
- Reporting fitted weights without their confidence intervals, or without comparing them with equal weights.
