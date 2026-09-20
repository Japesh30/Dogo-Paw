# Dogo-Paw — End-to-End QA Report

**Date:** 2026-09-20 · **Phase:** 8 (complete QA pass)

---

## Result

| | |
|---|---|
| **Tests executed** | **112** |
| **PASS** | **112** |
| **FAIL** | **0** |
| **BLOCKED** | **0** |
| **Bugs found requiring a code fix** | **0** |

Every one of the 50 required test areas was **actually executed**. Nothing is
claimed as passing on inspection alone.

Three tests failed on the first browser run. All three were **defects in the
test harness, not the application** — confirmed by inspecting the live DOM
before changing anything. Details in §6; no application code was changed as a
result, and nothing was marked PASS until the corrected test genuinely passed.

---

## 1. How these tests were run

This was not a static review. A full stack was stood up and driven end to end.

| Layer | What actually ran |
|---|---|
| **Backend** | The real Flask app, over HTTP on `:5001`, with `CORS_ORIGINS` set to the frontend origin |
| **Frontend** | The **production build** (`npm run build`), not the dev server |
| **Web server** | A server replicating Vercel's routing order — filesystem first, then the SPA rewrite |
| **Browser** | **Headless Chromium via Playwright**, at desktop (1440px) and mobile (375px, touch, iPhone UA) |
| **Database** | SQLite, exercised through the real API |

The frontend was built with `VITE_API_URL=http://127.0.0.1:5001`, so the browser
made **genuine cross-origin requests** to the backend and real CORS applied.

> Playwright and its Chromium build live outside the project, in a scratch
> directory and the user-level browser cache. **No dependency was added to
> `package.json` or `requirements.txt`**, and both are unchanged.

### Suites

| Suite | Tests | Covers |
|---|---|---|
| `qa_backend.py` | 59 | Tests 3–43: API, auth, authorization, database, ML |
| `qa_frontend.mjs` | 44 | Tests 1–12, 43–50, accessibility — real browser |
| `qa_admin.mjs` | 9 | Test 24 and the admin dashboard in a browser |
| Pre-existing regression suites | — | recommender (16), workflow (77), security (69), PG compat (41), `verify_db` (31), `api.js` (15), render checks (16) |

---

## 2. Public (tests 1–12)

| # | Test | Status | Evidence |
|---|---|---|---|
| 1 | Home page | **PASS** | Renders with header/nav; title `Rescue, Foster, Adopt · Dogo-Paw`; **no JS errors** |
| 2 | Navigation | **PASS** | 31 internal links; `/dogs` and `/adopt-match` reachable |
| 3 | Dogs page | **PASS** | 18 dogs fetched from the API; **no broken images**; disclosure shown |
| 4 | Dog filtering | **PASS** | "Small" narrowed 18 → 5; "Clear filters" restored all 18 |
| 5 | Dog search | **PASS** | "Luna" → 1 result; a non-matching term shows the empty state |
| 6 | Dog profile | **PASS** | `/dogs/3` renders `h1="Luna"`; title `Dog profile · Dogo-Paw`; disclosure shown |
| 7 | Invalid dog | **PASS** | `/dogs/9999` shows "We could not load that dog" — no crash. API returns 404 JSON, including for `/api/dogs/abc` |
| 8 | Adoption matcher | **PASS** | Questionnaire submitted; "Your results" with 20 result blocks; disclosure shown |
| 9 | Adoption validation | **PASS** | Empty submit produced **5 field errors**; API rejects bad enums, missing fields and wrong types with 400 |
| 10 | Volunteer form | **PASS** | Privacy notice shown **before** submit; client validation fires; submission reached the API and persisted |
| 11 | Chatbot | **PASS** | Widget opens, question answered; gibberish → low confidence + suggestions rather than a bluff |
| 12 | 404 page | **PASS** | "This page has wandered off" with a route home. Login page contains **no** demo credentials in the production build |

---

## 3. Authentication (13–21)

| # | Test | Status | Evidence |
|---|---|---|---|
| 13 | Registration | **PASS** | 201 + token via API; **also completed through the browser UI** |
| 14 | Duplicate registration | **PASS** | 409 |
| 15 | Invalid registration | **PASS** | Bad email, short password and blank name each → 400 |
| 16 | Login | **PASS** | 200 + token |
| 17 | Wrong password | **PASS** | 401 |
| 18 | Wrong email | **PASS** | 401 — and the error text is **identical** to the wrong-password case, so it is not a user-enumeration oracle |
| 19 | Logout | **PASS** | `revoked: true`; the same token then 401. Browser logout ends the session |
| 20 | Expired JWT | **PASS** | A token forged with the app's own key and a past `exp` → 401 |
| 21 | Revoked JWT | **PASS** | A valid, unexpired token refused after logout. Also: tampered signature → 401, `alg:none` forgery → 401 |

---

## 4. Authorization (22–26)

| # | Test | Status | Evidence |
|---|---|---|---|
| 22 | Normal user → admin | **PASS** | API 403 on both admin routes. In the browser: "Admin access only", **no dashboard data rendered** |
| 23 | Guest → admin | **PASS** | API 401 on both routes. Browser redirects to `/login` |
| 24 | Admin → admin | **PASS** | Dashboard renders totals, the 7-day chart (18 SVG elements), k-means segments, FAQ activity and the match-request table — **with no JS errors** |
| 25 | Admin API access | **PASS** | Payload carries `totals`, `activity`, `top_dogs`, `recent_activity`, `chatbot` |
| 26 | Normal user → admin API | **PASS** | 403 body is `{"error": ...}` only — **no leaked dashboard fields** |

---

## 5. Database (27–32)

| # | Test | Status | Evidence |
|---|---|---|---|
| 27 | User creation | **PASS** | Row written; password stored as a `scrypt:` hash — the plaintext appears nowhere |
| 28 | Adopter profile | **PASS** | Row count incremented by exactly 1 per `/api/recommend` |
| 29 | Match request | **PASS** | Row with `top_dog_id`, `top_score`, `results_count = 18`; relationships resolve |
| 30 | Volunteer record | **PASS** | All six fields persisted |
| 31 | Chatbot log | **PASS** | Intent + confidence in range |
| 32 | Revoked token | **PASS** | Rows present with an expiry. Timestamps are naive UTC and serialise with a `Z` suffix |

---

## 6. ML (33–36)

| # | Test | Status | Evidence |
|---|---|---|---|
| 33 | Recommender | **PASS** | 18 ranked, scores within 0–100, every result carries reasons/concerns/penalties; kid-unfriendly dogs penalised for a family |
| 34 | Success prediction | **PASS** | A probability on every match (batch) and via the single-pair endpoint; `/api/model-info` serves metrics + coefficients |
| 35 | Segmentation | **PASS** | k-means returns k ≥ 2 with a silhouette score and **unique** labels |
| 36 | FAQ classifier | **PASS** | 7 intents, reported test accuracy **0.75**; 4/4 canonical questions routed correctly |

---

## 7. API (37–43)

| # | Test | Status | Evidence |
|---|---|---|---|
| 37 | Health endpoint | **PASS** | 200 `{"status":"ok"}`; touches no database, so a DB blip cannot cause a restart loop |
| 38 | Invalid JSON | **PASS** | Malformed bodies → 4xx on **all six** POST endpoints; **never 500** |
| 39 | Missing fields | **PASS** | 400 with a message |
| 40 | Oversized input | **PASS** | 200 KB body → **413 before parsing**; over-length fields → 400 |
| 41 | Invalid enum values | **PASS** | 400 on `/api/recommend` and `/api/predict-success` |
| 42 | Rate limiting | **PASS** | Login: 10 allowed, 11th → **429 with `Retry-After`**. Reads (`/api/dogs` ×25) never limited |
| 43 | CORS | **PASS** | **Over real cross-origin HTTP:** configured origin received `Access-Control-Allow-Origin`; `https://evil.example.com` received **no such header** |

---

## 8. Frontend (44–50)

| # | Test | Status | Evidence |
|---|---|---|---|
| 44 | Desktop | **PASS** | 1440×900 — horizontal overflow **0px** |
| 45 | Mobile | **PASS** | 375×812 touch — **zero horizontal overflow across all 8 public routes**; menu control present; **no tap target under 24px** |
| 46 | Refresh on nested route | **PASS** | `/dogs/5` reloaded and rendered — the SPA rewrite works. `/dogs/dog-01.jpg` still served as `image/jpeg`, **not shadowed** |
| 47 | API unavailable | **PASS** | With all `/api/**` aborted, a readable "Could not reach the server" message appears — no blank page, no crash. **Production copy: no "port 5001"** |
| 48 | Loading states | **PASS** | With a 2.5s delay injected, the spinner / `role="status"` is visible while in flight |
| 49 | Empty states | **PASS** | No-match search shows the empty state **with a "Show all" recovery action** |
| 50 | Error states | **PASS** | A forced 500 surfaces the API's message inside `role="alert"`, and **leaks no stack trace** |

### Accessibility basics

| Check | Status | Evidence |
|---|---|---|
| `html[lang]` | **PASS** | `en` |
| Image alt text | **PASS** | Every `<img>` has an `alt` attribute |
| Landmarks | **PASS** | Exactly one `<h1>`, a `<main>` landmark |
| Skip link | **PASS** | Present, and it is the **first Tab stop** |

---

## 9. The three first-run failures

Reported in full because "the test was wrong" is a claim that has to be
evidenced, not asserted.

### F-1 · Test 8 — "Adoption matcher returns ranked results"

- **First run:** FAIL
- **Root cause:** **Test harness.** The questionnaire's radio inputs are
  `class="sr-only"` with the visible `<label>` acting as the control — a normal
  accessible pattern. The harness tried `getByRole('radio', { name: … })` and
  then a direct `.check()`, and Playwright correctly refused: the label
  intercepts the pointer event. The form was therefore never filled, so no
  results appeared.
- **How it was diagnosed:** the live DOM was dumped before any change. It showed
  `<input type="radio" name="activity_level" value="medium" class="sr-only">` —
  real, correctly named inputs. The application markup was fine.
- **Fix:** the harness now clicks the `<label>`, which is what a real user
  clicks.
- **Application change:** **none.**
- **Severity:** none (not an application defect).

### F-2 · Test 8.1 — "Matcher results carry the disclosure"

Same root cause as F-1 — results never rendered, so the disclosure could not be
found. Passes once the form is filled. No application change.

### F-3 · Test 11 — "Chatbot opens and answers"

- **Root cause:** **Test harness.** The toggle's accessible name is
  `"Open the help assistant"`; the selector looked for `aria-label*="hat"`
  (expecting "chat") and matched nothing.
- **Fix:** selector changed to `aria-label*="assistant"`.
- **Application change:** **none.** The widget's label is arguably *better*
  than "chat" — it describes purpose rather than mechanism.
- **Severity:** none.

> **No critical or high-severity issues were found, so no fixes were required.**
> The instruction to fix such issues stands unused because the tests did not
> surface any — not because fixing was skipped.

---

## 10. Regression suites re-run after QA

All pre-existing suites were re-run at the end of this phase:

| Suite | Tests | Result |
|---|---|---|
| Recommender property tests | 16 | ✅ PASS |
| API workflow | 77 | ✅ PASS |
| Security | 69 | ✅ PASS |
| PostgreSQL compatibility | 41 | ✅ PASS |
| `verify_db.py` (SQLite) | 31 | ✅ PASS |
| `api.js` error handling | 6 | ✅ PASS |
| `api.js` URL construction | 9 | ✅ PASS |
| Rendered-HTML disclosure/privacy | 16 | ✅ PASS |
| Frontend lint | — | ✅ clean |
| Frontend production build | — | ✅ 1.24s |

**No regressions.**

---

## 11. What this QA did *not* cover

Stated so the report is not read as broader than it is.

| Not covered | Why | Risk |
|---|---|---|
| **Live Supabase PostgreSQL** | No credentials available. All DB tests ran on SQLite | **The main remaining unknown.** Compatibility was verified offline (41 checks) and `verify_db.py` is ready to run against Supabase — see [`DATABASE.md`](DATABASE.md) §10 |
| **Deployed Render / Vercel** | Nothing is deployed yet | Routing, CORS and the production build were verified against faithful local equivalents, but only the real platforms confirm |
| **Gunicorn serving** | Does not run on Windows | Config validated; the same WSGI object was served over HTTP |
| **Python 3.13** | Only 3.14.3 installed here; the deployment pins 3.13.7 | Low — dependencies pinned exactly, pickles are protocol 5 |
| **Real mobile hardware** | Emulated at 375px with touch and an iPhone UA | Low, but worth one real-device check before the viva |
| **Firefox / Safari** | Chromium only | Low — no browser-specific APIs are used |
| **Load and soak testing** | Out of scope for a college project | Rate limits are the only throttle; a free instance is not sized for load |
| **Automated accessibility audit** (axe) | Basics checked manually | Medium confidence rather than high. Structure, alt text, landmarks, focus order and tap targets all pass |

---

## 12. Reproducing this

```bash
# 1. Backend, with CORS pointed at the test frontend
cd app/backend
RATE_LIMIT_ENABLED=false CORS_ORIGINS="http://127.0.0.1:4173" python app.py

# 2. Production frontend build, pointed at that backend
cd app/frontend
VITE_API_URL="http://127.0.0.1:5001" npm run build

# 3. Serve dist with Vercel's routing order (filesystem, then SPA rewrite),
#    then drive it with Playwright.
```

The backend suite needs no servers — it drives the Flask test client directly:

```bash
cd app/backend
python test_recommender.py
python verify_db.py
```
