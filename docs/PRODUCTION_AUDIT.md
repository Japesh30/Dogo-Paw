# Dogo-Paw — Production Readiness Audit

**Date:** 2026-09-20
**Scope:** Full local audit of the existing repository prior to public deployment
(Vercel + Render + Supabase PostgreSQL).
**Status:** Phase 1 audit · Phase 2 stability pass · **Phase 3 security hardening** — all complete.
See [§12 — Phase 2](#12--phase-2-stability-and-bug-fixes) and
[§13 — Phase 3](#13--phase-3-security-hardening-status) for what changed.
The full security model now lives in [`SECURITY.md`](SECURITY.md).

The application is **functionally complete and locally healthy** — every test
passes, the build is clean, and all 14 API endpoints behave correctly including
their error and authorization paths. It is **not currently deployable**, for
configuration reasons rather than code-quality ones: there is no git
repository, no PostgreSQL driver, no WSGI server, and the login page publishes
working admin credentials.

---

## 1. Current architecture

```
D:\Dogo-Paw ITR\
├─ README.md                  project-level documentation
├─ .gitignore                 node_modules, .venv, dist, *.db, .secret_key, .env
├─ docs/PRODUCTION_AUDIT.md   this file
└─ app/
   ├─ README.md               deeper technical notes + API table
   ├─ frontend/               React 19 + Vite 8 + Tailwind 4 + React Router 7
   │  ├─ src/pages/           11 route components
   │  ├─ src/components/      14 shared components
   │  ├─ src/context/         AuthProvider + useAuth hook
   │  ├─ src/lib/             api.js, dogs.js, matchSession.js
   │  ├─ src/assets/          bundled images (4.1 MB)
   │  ├─ public/              logo, 18 generated dog photos, 29.9 MB video
   │  └─ scripts/             image optimiser, dog-photo builder
   └─ backend/                Flask 3 + SQLAlchemy 2 + SQLite
      ├─ app.py               app factory + all 14 routes (607 lines)
      ├─ models.py            7 tables
      ├─ auth.py              JWT issue/decode/revoke + route decorators
      ├─ recommender.py       distance-based matching engine
      ├─ seed.py              18 dogs, bios, 2 default accounts, mini-migration
      ├─ demo_data.py         optional dashboard backfill
      ├─ clean_test_data.py   optional test-row cleanup
      ├─ test_recommender.py  16 property checks
      └─ ml/
         ├─ features.py       shared encoding, imported from recommender.py
         ├─ success_model.py  LogisticRegression
         ├─ segmentation.py   KMeans
         ├─ chatbot.py        TF-IDF + MultinomialNB
         └─ artifacts/        3 committed trained artifacts (466 KB)
```

**Separation of concerns is good.** `ml/features.py` imports its 0–1 scales
directly from `recommender.py` rather than redefining them, so the recommender,
the success model and the clustering can never disagree about what "medium
activity" means. This is a genuine strength and is worth stating in the viva.

### Answers to the 20 audit questions

| # | Question | Answer |
|---|---|---|
| 1 | **How the frontend starts** | `cd app/frontend && npm install && npm run dev` → Vite dev server |
| 2 | **How the backend starts** | `cd app/backend && python app.py` → Flask dev server (`app.run(debug=True)`, `app.py:607`) |
| 3 | **Ports** | Frontend `5173` (pinned in `vite.config.js`), backend `5001` (`PORT` env, default 5001) |
| 4 | **Frontend ↔ backend** | Dev: Vite proxies `/api/*` → `http://127.0.0.1:5001` (`vite.config.js`). Prod: `api.js:2` reads `VITE_API_URL`, falling back to `''`. Auth via `Authorization: Bearer <jwt>` |
| 5 | **Database** | SQLite file `dogopaw.db`, via Flask-SQLAlchemy. 7 tables (schema below) |
| 6 | **Authentication** | JWT HS256, 7-day TTL, `jti` per token, `werkzeug` password hashing, server-side revocation denylist |
| 7 | **Admin authorization** | Double-guarded: `ProtectedRoute requireAdmin` on the client, `@admin_required` on the server (`auth.py:104`) |
| 8 | **Public endpoints** | 8 (see §"API surface") |
| 9 | **Authenticated endpoints** | 2 strictly (`/api/auth/me`, `/api/auth/logout`); 2 optional-auth (`/api/recommend`, `/api/chatbot`) |
| 10 | **Admin endpoints** | 2 (`/api/admin/stats`, `/api/admin/adopter-segments`) |
| 11 | **ML model loading** | Warmed once at startup by `MODEL_LOADERS` (`app.py:50`), cached in a module global, never loaded on a request. Missing artifact = warning, not crash |
| 12 | **Recommender** | Euclidean distance in normalised `[energy, space, experience]` space, `score = (1 - d/√3) × 100`, then ×0.4 kids / ×0.5 pets safety multipliers |
| 13 | **Chatbot** | TF-IDF (word + char n-grams) → MultinomialNB over 7 intents; below 0.40 confidence it returns an honest fallback rather than guessing |
| 14 | **Volunteer submissions** | `POST /api/volunteer` → full server-side re-validation → `volunteers` table; every client rule is re-checked server-side |
| 15 | **Seed/demo data** | `seed()` runs inside `create_app()` on every boot; `demo_data.py` optionally backfills ~40 real recommendations with backdated timestamps |
| 16 | **Environment variables** | `SECRET_KEY`, `DATABASE_URL`, `CORS_ORIGINS`, `PORT` (backend); `VITE_API_URL` (frontend) |
| 17 | **Dependencies** | 10 pinned Python packages; 4 runtime + 8 dev npm packages |
| 18 | **Production deployment possible?** | **No** — 5 hard blockers, see §Deployment blockers |
| 19 | **Security issues?** | **Yes** — 1 critical, 3 high, see §Security findings |
| 20 | **Broken/incomplete features?** | **No broken features.** Everything documented works. Only deployment-shaped gaps |

---

## 2. Frontend status

**Verdict: healthy. No code defects found.**

| Check | Command | Result |
|---|---|---|
| Install | `npm install` | ✅ exit 0, 0 vulnerabilities (`npm audit --omit=dev`) |
| Lint | `npm run lint` (oxlint) | ✅ **clean — 0 warnings, 0 errors** |
| Build | `npm run build` | ✅ **built in 6.80s** |

Build output:

```
dist/assets/index-BkOGMQbh.js    689.02 kB │ gzip: 204.29 kB
dist/assets/index-JpXGDCyy.css    52.87 kB │ gzip:   8.93 kB
dist/ total                       34 MB (29.9 MB of that is one video)
```

Observations:

- `src/lib/api.js` is already production-aware — `VITE_API_URL` needs only to be
  set on Vercel. No code change required for the API base URL.
- `AuthProvider` correctly re-hydrates the session on refresh via `/api/auth/me`
  and clears a rejected token.
- `matchSession.js` deliberately caches results in `sessionStorage` so that
  browsing dog pages does not write phantom `MatchRequest` audit rows. This is a
  thoughtful decision, well commented, and worth raising in the viva.
- Every `sessionStorage`/`localStorage` access is wrapped in `try/catch`, so
  private-browsing mode degrades rather than crashing.
- **689 kB single JS chunk** (204 kB gzipped) — above Vite's 500 kB warning
  threshold, driven mainly by Recharts on the admin page. Not a blocker; noted
  as LOW.
- **No `vercel.json`** — React Router deep links (`/dogs/3`, `/admin`) will
  return 404 on Vercel without an SPA rewrite. HIGH.
- The offline error message in `api.js:10` tells the user to "make sure the
  Flask backend is running on port 5001" — wrong advice on a public site. LOW.

---

## 3. Backend status

**Verdict: healthy. All modules import, all endpoints behave correctly.**

| Check | Command | Result |
|---|---|---|
| Dependency install | `pip install -r requirements.txt` | ✅ all 10 resolved on Python 3.14.3 |
| Byte-compile | `python -m compileall -q .` | ✅ **OK** — no syntax errors |
| Import check | all 11 modules | ✅ **OK** — no circular imports, no import-time failures |
| Recommender tests | `python test_recommender.py` | ✅ **ALL CHECKS PASSED (16/16)** |
| Endpoint smoke test | Flask test client | ✅ **14/14 correct** |

### API surface (all 14 endpoints verified)

| Method | Path | Auth | Verified response |
|---|---|---|---|
| POST | `/api/auth/register` | — | 201 / 400 / 409 |
| POST | `/api/auth/login` | — | ✅ 200, 401 on bad password |
| GET | `/api/auth/me` | **bearer** | ✅ 200 with token, 401 without |
| POST | `/api/auth/logout` | bearer | ✅ `{"revoked": true}`, token then rejected |
| GET | `/api/dogs` | — | ✅ 200, `count: 18` |
| GET | `/api/dogs/<id>` | — | ✅ 200; **404** on id 999 |
| POST | `/api/volunteer` | — | ✅ 201; **400** on missing fields |
| POST | `/api/recommend` | optional | ✅ 200, `count: 18`; **400** on invalid enum |
| POST | `/api/predict-success` | — | ✅ 200 |
| GET | `/api/model-info` | — | ✅ 200 |
| POST | `/api/chatbot` | optional | ✅ 200, intent `adoption_process` @ 0.9989 |
| GET | `/api/admin/stats` | **admin** | ✅ 200 as admin; **401** anonymous; **403** as non-admin |
| GET | `/api/admin/adopter-segments` | **admin** | ✅ **401** anonymous |
| GET | `/api/health` | — | ✅ 200 |

**Authorization is correctly enforced server-side.** The 401/403 distinction is
right, revocation genuinely works (a logged-out token was rejected on the next
request), and no admin data leaks to a non-admin. This is the part of the
project most likely to be probed in a viva, and it holds up.

### Backend structural notes

- `app = create_app()` runs at **module import** (`app.py:604`). This is
  compatible with `gunicorn app:app`, but it means `seed()` also runs on every
  worker boot — see the seed race under Deployment blockers.
- `resolve_secret_key()` writes a generated key to `.secret_key` on disk. Sound
  for local zero-config use; unusable on Render's ephemeral filesystem.
- `ensure_columns()` in `seed.py:357` uses portable `ALTER TABLE ... ADD COLUMN`
  and is PostgreSQL-safe as written. No change needed.
- Local variable `payload` shadows the module-level `payload()` helper inside the
  `logout()` route (`app.py:188`). Harmless today — the helper is not called
  after the shadow — but it is a latent trap. LOW.

---

## 4. Database status

**Technology:** SQLite (`app/backend/dogopaw.db`), created and seeded on first
run. Not committed (gitignored).

**Schema — 7 tables:**

| Table | Key columns | Notes |
|---|---|---|
| `users` | id, name, email (unique, indexed), password_hash, is_admin, created_at | |
| `dogs` | id, name, age, energy_level, size, temperament, medical_needs, good_with_kids, good_with_other_pets, photo_url, bio | 18 rows, seeded |
| `adopters` | id, user_id (FK, nullable), activity_level, home_type, experience_level, has_kids, has_other_pets | nullable FK so guests can match |
| `match_requests` | id, user_id (FK), adopter_id (FK), top_dog_id (FK), top_score, results_count, created_at (indexed) | audit row per `/api/recommend` |
| `volunteers` | id, name, email (indexed), mobile, address, state, city, submitted_at (indexed) | |
| `chatbot_logs` | id, user_id (FK), question, predicted_intent (indexed), confidence, low_confidence, created_at (indexed) | doubles as an evaluation set |
| `revoked_tokens` | id, jti (unique, indexed), expires_at (indexed), revoked_at | JWT denylist, self-pruning |

**Seeding:** `seed()` inserts 18 dogs and 2 accounts if empty, then re-syncs
seed-owned `photo_url`/`bio` on every boot. Timestamps are stored **naive UTC**
and serialised with an explicit `Z` suffix by `iso_utc()` — correct and
consistent, and it will carry over to PostgreSQL unchanged.

**PostgreSQL readiness:** the ORM usage is portable (`func.avg`, `func.count`,
`group_by`, `like`, datetime comparisons — nothing SQLite-specific). The
blockers are the missing driver and the URI scheme, not the queries.

---

## 5. Authentication status

**Verdict: well designed. Stronger than typical for a project of this scope.**

Flow:

1. `POST /api/auth/register` or `/login` → server returns a JWT (HS256, 7-day
   TTL) carrying `sub`, `email`, `is_admin`, `jti`, `iat`, `exp`.
2. React `AuthProvider` stores it in `localStorage` under `dogopaw.token`.
3. Every authenticated call sends `Authorization: Bearer <token>`.
4. `load_user()` runs as a `before_request` hook, resolving the token to a `User`
   on `flask.g` — or `None` if absent, invalid, **or revoked**.
5. `POST /api/auth/logout` writes the token's `jti` to `revoked_tokens`.
   Expired rows are pruned on each revocation.

Strengths (verified by execution, not just by reading):

- Passwords hashed with `werkzeug.security`; plaintext never stored.
- **Real server-side revocation.** A JWT is normally un-invalidatable because the
  server holds no session; the `jti` denylist closes that gap. Confirmed: after
  logout, the same token returned **401**.
- Admin route guarded on the server, where it matters, not only in React.
- `login_required` / `admin_required` return the correct 401 vs 403.

Gaps (all HIGH/MEDIUM, none broken):

- **No rate limiting** on `/api/auth/login` — unlimited password guessing.
- **No request size cap** (`MAX_CONTENT_LENGTH` unset).
- Token in `localStorage` is XSS-readable. Acceptable and defensible for this
  project; worth being able to explain the trade-off in the viva.
- Ephemeral `SECRET_KEY` on Render would silently sign every user out on each
  deploy.

---

## 6. ML status

**Verdict: all four components load and run. Metrics reproduce exactly as
documented in the README.**

| Component | Paradigm | Model | Loading | Verified metric |
|---|---|---|---|---|
| Adoption matching | distance-based | euclidean in 3-D | pure Python, no artifact | **16/16 property checks pass** |
| Adoption success | supervised | LogisticRegression | `success_model.joblib` (2.2 KB), warmed at startup | test **65.33%**, CV **69.0%**, AUC **0.7564**, ceiling 70.06% → **98.49% of ceiling** |
| Adopter segments | unsupervised | KMeans | trained on request, no artifact | k by silhouette; degrades honestly below 3 profiles |
| FAQ assistant | NLP | TF-IDF + MultinomialNB | `chatbot_model.joblib` (462 KB), warmed at startup | test **75.0%** on 20 unseen phrasings, **90.0%** useful-response rate, 7 intents, 156 training examples |

Verified behaviours:

- Artifacts are **committed to the repo** and are not gitignored — they will
  deploy with the backend. No training step is needed on Render. ✅
- Both artifacts load cleanly under **scikit-learn 1.9.0** (the pinned version).
- Models are loaded **once at startup**, cached in a module global. No request
  pays a load cost. ✅
- A missing artifact produces a startup **warning**, not a crash, and the routes
  return 503 rather than 500. Good degradation design.
- `segmentation.segment()` with 1 adopter correctly returned
  `{"available": false, "reason": "Need at least 3 adopter profiles..."}`
  instead of raising. ✅
- Cluster names are **derived from centroids**, not hardcoded to cluster
  numbers, so they follow the data rather than going silently wrong when
  clusters renumber. Good design; worth mentioning in the viva.

**Deployment risk:** the `.joblib` artifacts are pickles tied to the scikit-learn
version that wrote them. `scikit-learn==1.9.0` must stay pinned, and Render's
Python version must have wheels for it. Un-pinning would break inference.

---

## 7. Testing status

| Suite | Command | Result |
|---|---|---|
| Recommender property tests | `python test_recommender.py` | ✅ **16/16 PASSED** |
| Byte-compile (all modules) | `python -m compileall -q .` | ✅ **OK** |
| Import check (11 modules) | `importlib.import_module` | ✅ **11/11 OK** |
| API endpoint smoke test | Flask test client | ✅ **14/14 correct** |
| Auth/authorization paths | Flask test client | ✅ **8/8 correct** |
| ML artifact load + metrics | direct calls | ✅ **all load, metrics match README** |
| Frontend lint | `npm run lint` | ✅ **clean** |
| Frontend build | `npm run build` | ✅ **success** |
| npm vulnerability audit | `npm audit --omit=dev` | ✅ **0 vulnerabilities** |

**Tests failed: none.**

**Coverage gaps (honest assessment):**

- `test_recommender.py` covers the recommender **only**. There are **no
  automated tests** for the API routes, authentication, the volunteer workflow,
  or the three `ml/` models. The 14-endpoint and 8-auth-path checks above were
  written ad hoc for this audit and are **not saved in the repo**.
- There is **no test runner** (no pytest, no `npm test`) and **no CI** (no
  `.github/`). `test_recommender.py` is a standalone script with its own
  pass/fail printing.
- This is acceptable for the current scope, but it means a deployment change
  could regress an endpoint with nothing to catch it.

---

## 8. Security findings

### 🔴 CRITICAL

**S-1 — Working admin credentials are printed on the public login page.**
`src/pages/Login.jsx:193-198` renders a "Demo accounts" panel containing
`admin@dogo-paw.org / admin123`. Those exact credentials are seeded by
`seed.py:346-350` and grant access to `/admin` — the full dashboard, every
adopter profile, every volunteer's name, email, phone number and home address,
and every chatbot question asked.

On a public deployment this is not a weak password; it is a **published** one.
Anyone who opens the login page has admin access. The same credentials also
appear in `README.md:79-80` and `app/README.md:59-60`, which will be public on
GitHub.

This is the single most serious finding in the audit and must be fixed before
the site is reachable from the internet.

### 🟠 HIGH

**S-2 — `debug=True` in the production entry point.** `app.py:607` runs
`app.run(debug=True, ...)`. If the app is ever started via `python app.py` on
Render, the Werkzeug interactive debugger is exposed, which permits arbitrary
code execution on the server. Fixing this is coupled to adding a proper WSGI
server (D-3).

**S-3 — `CORS_ORIGINS` defaults to `*`.** `app.py:94`. With a wildcard origin any
website can call the API from a visitor's browser. It must be pinned to the
Vercel domain in production.

**S-4 — No rate limiting on authentication.** `/api/auth/login` and
`/api/auth/register` accept unlimited attempts. Combined with 6-character
minimum passwords, online brute-forcing is unimpeded. `/api/recommend` and
`/api/chatbot` are also unthrottled and each write a database row per call, so
they can be used to inflate the dashboard or fill the database.

### 🟡 MEDIUM

**S-5 — Ephemeral signing key.** With no `SECRET_KEY` env var, `app.py:71-82`
generates one onto disk. Render's filesystem does not survive a restart, so the
key would change on every deploy, invalidating every issued JWT and signing all
users out without explanation. It also means multiple instances could not
validate each other's tokens.

**S-6 — No request size limit.** `MAX_CONTENT_LENGTH` is unset, so an arbitrarily
large JSON body is read into memory. The 500-character cap on `/api/chatbot` is
applied *after* parsing, not before.

**S-7 — JWT stored in `localStorage`.** Readable by any injected script. React
escapes by default and no `dangerouslySetInnerHTML` was found, so exploitability
is low — but this is a known trade-off you should be ready to defend rather than
be surprised by.

### 🟢 LOW

**S-8 — Chatbot logs store raw visitor questions** (`chatbot_logs.question`) with
no retention limit. Fine for a project; worth acknowledging as a privacy note.

**S-9 — Volunteer PII stored in plaintext** — name, email, phone, home address.
Appropriate for the use case, but combined with S-1 it is what makes S-1 severe.

**Clean results:** no hardcoded API keys, passwords or tokens were found in
application source (only the seed defaults and the login-page panel above). No
`.env` file is committed. `npm audit` reports 0 vulnerabilities.

---

## 9. Deployment blockers

### 🔴 CRITICAL — deployment is impossible until these are resolved

**D-1 — Not a git repository.** `git rev-parse` returns *"not a git
repository"*. Vercel and Render both deploy from a git remote. Nothing can be
deployed at all until `git init`, an initial commit, and a GitHub remote exist.
This is the first blocker in the chain — every other fix depends on it.

**D-2 — No PostgreSQL driver.** `requirements.txt` contains no `psycopg` or
`psycopg2-binary`. Pointing `DATABASE_URL` at Supabase will fail immediately with
a SQLAlchemy "Can't load plugin" error at startup.

**D-3 — No WSGI server.** The only entry point is Flask's development server
(`app.py:607`), and `gunicorn` is not in `requirements.txt`. Render has no
process to start. This blocker and S-2 (`debug=True`) are fixed together.

**D-4 — `postgres://` URI scheme.** `app.py:89` passes `DATABASE_URL` through
untouched. Supabase and Render commonly issue `postgres://…`, which SQLAlchemy 2
rejects outright; it requires `postgresql://` (or `postgresql+psycopg://`). A
normalisation step is needed.

**D-5 — No SPA rewrite for Vercel.** There is no `vercel.json`. Direct
navigation or a refresh on `/dogs/3`, `/adopt-match` or `/admin` will return a
Vercel 404, because those paths exist only in React Router. Internal navigation
would work, so this fails exactly when a viva examiner reloads a deep page.

### 🟠 HIGH

**D-6 — `SECRET_KEY` not enforced in production.** See S-5. The code supports the
env var; nothing requires it or warns when it is absent.

**D-7 — No `pool_pre_ping` / connection recycling.** Render's free tier sleeps
and Supabase's pooler drops idle connections. Without `pool_pre_ping=True` the
first request after an idle period raises a stale-connection error rather than
reconnecting. This will look like a broken site during a demo.

**D-8 — `seed()` runs on every worker boot.** `create_app()` calls `seed()` at
import time (`app.py:98-101`). With SQLite and one process this is harmless; with
multiple gunicorn workers starting simultaneously against PostgreSQL, they race
on `create_all()` and the initial inserts, which can raise duplicate-key errors
on first deploy.

**D-9 — No Python version pin.** No `runtime.txt` or `.python-version`. Render
picks its own default, which may not have wheels for the pinned
`numpy==2.5.1` / `scipy==1.18.0` / `scikit-learn==1.9.0`. A source build of scipy
on a free instance will exhaust the build timeout. Verified locally on Python
3.14.3, where all three had wheels.

**D-10 — No `.env.example` for the frontend.** `VITE_API_URL` is read by
`api.js:2` but is documented nowhere, so the Vercel setting is easy to miss.

### 🟡 MEDIUM

**D-11 — Documentation contradicts the target deployment.** `README.md` states
the database is SQLite and that "**No `.env` file is needed**". After deployment
this is wrong in three places, and the README is what an examiner reads first.

**D-12 — 29.9 MB `video-1.mp4`** in `public/media/`. Within Vercel's per-file
limit, but it makes the repository ~30 MB, slows every push and every build, and
is the dominant cost in the 34 MB `dist/`.

**D-13 — Render free-tier cold start.** Instances sleep after ~15 minutes idle
and take ~50 s to wake. The first request will hit `api.js`'s offline message and
look like a broken backend. Needs either a mitigation or a prepared explanation.

### 🟢 LOW

**D-14 — 689 kB JS chunk.** Above Vite's warning threshold, mostly Recharts.
Loads fine; only a performance nicety.

**D-15 — Frontend offline message names "port 5001"** (`api.js:10`) — incorrect
user-facing copy in production.

**D-16 — No automated API tests and no CI.** Deployment changes will touch
`create_app()`, config and the database layer with no regression net.

---

## 10. Recommended fixes

### Priority classification

| ID | Finding | Priority | Effort |
|---|---|---|---|
| S-1 | Admin credentials published on login page + in both READMEs | **CRITICAL** | S |
| D-1 | No git repository | **CRITICAL** | S |
| D-2 | No PostgreSQL driver | **CRITICAL** | S |
| D-3 | No WSGI server (gunicorn) | **CRITICAL** | S |
| D-4 | `postgres://` URI not normalised | **CRITICAL** | S |
| D-5 | No Vercel SPA rewrite | **CRITICAL** | S |
| S-2 | `debug=True` in entry point | **HIGH** | S |
| S-3 | `CORS_ORIGINS` defaults to `*` | **HIGH** | S |
| S-4 | No rate limiting on auth | **HIGH** | M |
| D-6 | `SECRET_KEY` not enforced in production | **HIGH** | S |
| D-7 | No `pool_pre_ping` | **HIGH** | S |
| D-8 | `seed()` races across gunicorn workers | **HIGH** | M |
| D-9 | No Python version pin | **HIGH** | S |
| D-10 | `VITE_API_URL` undocumented | **HIGH** | S |
| S-5 | Ephemeral signing key | **MEDIUM** | S |
| S-6 | No request size limit | **MEDIUM** | S |
| S-7 | JWT in `localStorage` | **MEDIUM** | — (accept + document) |
| D-11 | README contradicts deployed reality | **MEDIUM** | M |
| D-12 | 29.9 MB video in repo | **MEDIUM** | S |
| D-13 | Render cold start | **MEDIUM** | S |
| S-8 | Chatbot question retention | **LOW** | — (document) |
| S-9 | Volunteer PII in plaintext | **LOW** | — (document) |
| D-14 | 689 kB JS chunk | **LOW** | M |
| D-15 | "port 5001" in production error copy | **LOW** | S |
| D-16 | No API tests, no CI | **LOW** | M |
| — | `payload` shadowed in `logout()` | **LOW** | S |

### Notes on the fixes

**S-1** should not be solved by deleting the demo-account panel outright — it is
genuinely useful for the viva, and rule 12 says not to remove working features
for deployment's sake. The defensible fix is to keep a demo account but make the
admin password an environment variable (`ADMIN_PASSWORD`) set only on Render, and
show the non-admin demo account on the login page. That preserves the
demonstration, removes the public admin access, and is straightforward to explain
to an examiner.

**D-8** is best fixed by moving `seed()` out of `create_app()` into an explicit
one-time step (a Render release/pre-deploy command), or by guarding it behind an
env flag. Both are small and explainable.

**S-4** needs judgement. `Flask-Limiter` is one dependency and is the standard
answer, but rule 7 says not to add unnecessary dependencies. A minimal in-memory
throttle on the login route is ~20 lines and adds nothing to `requirements.txt`.
I would recommend the in-memory version and flag the trade-off (it does not
survive a restart or span instances) rather than pulling in a library for a
single-instance free-tier deployment. **Your call — I will ask before
implementing.**

---

## 11. Recommended order of fixes

Ordered by dependency, not just by severity. Each phase leaves the project in a
working, testable state.

**Phase 2 — Security hardening (do this before anything is public)**
S-1 (admin credentials), S-2 (`debug=True`), S-6 (request size cap).
*Nothing should reach the internet until S-1 is closed.*

**Phase 3 — Production configuration**
D-4 (URI normalisation), D-6 (`SECRET_KEY` enforcement), S-3 (`CORS_ORIGINS`),
D-7 (`pool_pre_ping`), S-5. All of these are changes to `create_app()` and can be
verified locally against SQLite before PostgreSQL is involved.

**Phase 4 — Database migration to PostgreSQL**
D-2 (driver), D-8 (seed race), then a local run against a real Supabase instance
to confirm the schema creates and seeds correctly.

**Phase 5 — Backend deployment scaffolding**
D-3 (gunicorn + start command), D-9 (Python pin), `render.yaml` / Render
settings, D-13 (cold-start handling).

**Phase 6 — Frontend deployment scaffolding**
D-5 (`vercel.json` SPA rewrite), D-10 (`.env.example`), D-15 (error copy),
optionally D-12 (video).

**Phase 7 — Repository and deployment**
D-1 (`git init`, `.gitignore` verification, GitHub remote), then deploy backend
to Render, then frontend to Vercel, then wire `CORS_ORIGINS` and `VITE_API_URL`
to the real domains.

**Phase 8 — Documentation and verification**
D-11 (README), a full end-to-end pass over all 14 endpoints against production,
and a viva-readiness check.

**Optional / if time allows**
S-4 (rate limiting), D-16 (API tests + CI), D-14 (code splitting).

> **Why D-1 is late despite being CRITICAL:** git init is trivial, but the
> *first commit should not contain published admin credentials*. Sequencing the
> security fix first keeps them out of the repository history, where they would
> otherwise be permanent.

---

## 12 — Phase 2: stability and bug fixes

**Date:** 2026-09-20 · **Scope:** bugs and broken functionality only. No
production/deployment changes were made, as instructed.

### Headline

Across the 12 priority areas (startup, API, build, auth, admin authz, dog
listing, matching, volunteer, chatbot, ML loading, database, routing),
**77 of 77 workflow checks passed and no functional failures were found.**

That is the honest result: the application was already stable. Rather than stop
there, I re-read in full the frontend files that Phase 1 had only surveyed
(`Dogs.jsx`, `DogProfile.jsx`, `AdoptMatch.jsx`, `Admin.jsx`, `charts.jsx`,
`lib/dogs.js`) and probed the API with 77 targeted cases including edge and
error paths. That second pass found **one real defect**, described below.

### Fixed issues

#### B-1 — Server error messages were replaced with a misleading "server is down" (FIXED)

**Severity:** MEDIUM · **File:** `app/frontend/src/lib/api.js`

**Root cause.** The request helper tested for HTTP 502/503/504 *before* parsing
the response body, and unconditionally threw its offline message:

```js
if (res.status === 502 || res.status === 503 || res.status === 504) {
  throw new ApiError(OFFLINE_MESSAGE, res.status)   // body never read
}
```

The backend, however, uses **503 itself** to report a missing ML artifact —
`app.py` returns `{"error": "The chatbot model has not been trained yet."}` with
status 503 from `/api/chatbot`, and the equivalent from `/api/predict-success`
and `/api/model-info`. Because the status was checked first, that real
explanation was discarded and the user was told *"Could not reach the server.
Make sure the Flask backend is running on port 5001"* — while the server was
running perfectly well. The message sent you to diagnose the wrong thing.

**Why it matters beyond today.** The artifacts are committed, so this is latent
locally. It gets worse in production: a sleeping Render instance also answers
503, so the two causes become genuinely ambiguous and the app needs to tell
them apart rather than assume.

**The fix (smallest correct change).** Parse the body first, then treat
502/503/504 as "unreachable" **only when there is no JSON `error` field**. A
dead proxy sends no JSON body; our own API always does. The body is what
distinguishes them.

```js
const unreachable = res.status === 502 || res.status === 503 || res.status === 504
if (unreachable && !payload?.error) {
  throw new ApiError(OFFLINE_MESSAGE, res.status)
}
```

No behaviour changed for any other status code, and genuine-offline detection
still works.

**Verification.** A 6-case harness drove `api.js` with a mocked `fetch`.
Before the fix: **2 failed**. After: **6/6 pass**, including both
genuine-offline cases.

| Case | Before | After |
|---|---|---|
| 503 + `{"error": "chatbot model not trained"}` | ❌ "server is down" | ✅ real message |
| 503 + `{"error": "success model not trained"}` | ❌ "server is down" | ✅ real message |
| 503, no JSON body (proxy dead) | ✅ offline | ✅ offline |
| 502, no JSON body (gateway dead) | ✅ offline | ✅ offline |
| 400 + validation error | ✅ real message | ✅ real message |
| 401 + auth error | ✅ real message | ✅ real message |

Server behaviour was confirmed to match: with the artifacts simulated missing,
`/api/chatbot` and `/api/predict-success` return **503 with
`Content-Type: application/json`**, and `/api/recommend` still returns **200**
with `success_probability: null` — the graceful degradation works as designed.

### Deliberately NOT changed

Kept out of scope on purpose, so Phase 2 stayed a stability pass:

| Item | Why not now |
|---|---|
| S-1 admin credentials, S-2 `debug=True`, S-3 CORS, S-6 size cap | Security hardening — **Phase 2 of the fix plan (§11)**, and the instruction was bugs only |
| All D-* items | Explicitly deferred: "do NOT perform production deployment changes yet" |
| `payload` shadowed in `logout()` (`app.py:188`) | A latent readability trap, **not** a defect — nothing calls the helper after the shadow. Fixing it would be unrelated refactoring |
| 689 kB JS chunk (D-14) | Performance nicety, not a bug |
| "port 5001" in the offline copy (D-15) | Real, but it is production *copy* — belongs with the frontend deployment phase |
| Saving the 77-check workflow harness into the repo (D-16) | Would be adding new functionality, not fixing a bug. **Recommended for a later phase** — see below |

### Remaining issues

Nothing from the Phase 1 audit has been resolved except B-1. All items in
§8 (Security) and §9 (Deployment blockers) stand exactly as written, including
every CRITICAL:

- **S-1** — admin credentials still published on the login page and in both
  READMEs. **Still the most urgent item in the project.**
- **D-1…D-5** — no git repo, no PostgreSQL driver, no WSGI server, `postgres://`
  not normalised, no Vercel SPA rewrite.
- **D-6…D-10** and all MEDIUM/LOW items — unchanged.

The recommended order of fixes in §11 is unchanged and remains valid.

### Test results — Phase 2

| Suite | Command | Result |
|---|---|---|
| Frontend lint | `npm run lint` | ✅ **clean** — 0 warnings, 0 errors |
| Frontend build | `npm run build` | ✅ **built in 1.25s**, 689.03 kB / 204.29 kB gzip |
| Backend byte-compile | `python -m compileall -q .` | ✅ **OK** |
| Recommender property tests | `python test_recommender.py` | ✅ **16/16 PASSED** |
| API workflow harness (new) | 77 checks, Flask test client | ✅ **77/77 PASSED** |
| `api.js` error-handling harness (new) | 6 checks, mocked fetch | ✅ **6/6 PASSED** (was 4/6) |

**Tests failed: none.**

Workflow coverage, by required endpoint:

| Endpoint | Checks | Result |
|---|---|---|
| `GET /api/health` | 1 | ✅ |
| `GET /api/dogs` | 4 (count, photo_url, bio, status) | ✅ |
| `GET /api/dogs/<id>` | 4 (valid, 999→404, `abc`→404, JSON body) | ✅ |
| `POST /api/auth/register` | 7 (201, email lowercased, dup→409, bad email, short password, blank name) | ✅ |
| `POST /api/auth/login` | 4 (case-insensitive email, wrong password→401, unknown→401, junk body) | ✅ |
| `POST /api/recommend` | 11 (all 18 ranked, sorted, 0–100, breakdown, success probability, penalties, guest, bad enum, coercion) | ✅ |
| `POST /api/chatbot` | 7 (intent correct, gibberish→low confidence + suggestions, empty→400, >500→400) | ✅ |
| `POST /api/volunteer` | 7 (201, persisted, each validation rule, formatted mobile) | ✅ |
| Authentication | 4 (token, no token, garbage token, malformed header) | ✅ |
| Admin authorization | 6 (anon→401, non-admin→403, admin→200, both admin routes) | ✅ |
| Logout / revocation | 4 (revoked, token dead after, idempotent, no-token) | ✅ |
| ML endpoints | 6 (`model-info`, by `dog_id`, bad id→404, inline dog, incomplete→400, missing→400) | ✅ |
| Segmentation | 4 (k-means over real profiles, k chosen, labels present and unique) | ✅ |
| Admin dashboard shape | 7 (7-day window, volunteers bucketed, totals, chatbot block, feed ordering, `Z` timestamps) | ✅ |

**Authentication and admin authorization are confirmed correct end to end:**
401 vs 403 are distinguished properly, a non-admin is refused both admin
routes, and a token is genuinely dead on the request after logout.

### Files changed in Phase 2

| File | Change |
|---|---|
| `app/frontend/src/lib/api.js` | Fixed B-1 — parse the body before deciding a 502/503/504 means "unreachable" (one reordered block, ~6 lines net, with a comment explaining why) |
| `docs/PRODUCTION_AUDIT.md` | This section |

**No backend file was modified.** No dependency was added or removed. No
feature was removed.

---

## 13 — Phase 3: security hardening status

**Date:** 2026-09-20. Full detail in [`SECURITY.md`](SECURITY.md); this is the
status of the Phase 1 findings only.

### Resolved

| ID | Finding | How |
|---|---|---|
| **S-1** | 🔴 **Admin credentials published on the login page** | Panel gated on `import.meta.env.DEV` so the bundler strips it from production builds; admin no longer named there at all. Admin password now from `ADMIN_PASSWORD` (required in production, min 12 chars); demo adopter not seeded in production. Both READMEs corrected. **Verified: zero credential strings in a fresh `dist/`.** |
| **S-2** | 🟠 `debug=True` in the entry point | `DEBUG` and `PROPAGATE_EXCEPTIONS` pinned `False` in config; the `__main__` block refuses to run when `APP_ENV=production` and points at `gunicorn app:app` |
| **S-3** | 🟠 `CORS_ORIGINS` defaults to `*` | `*` and unset both refused in production; development falls back to the two localhost origins. **Verified over HTTP: allowed origin gets `Access-Control-Allow-Origin`, an unknown origin gets none** |
| **S-4** | 🟠 No rate limiting on authentication | `ratelimit.py` — login 10/15min, register 5/hr, chatbot 20/min, recommend 10/min, volunteer 5/hr. **Verified over HTTP: 10 through, then 429 with `Retry-After: 899`** |
| **S-5** | 🟡 Ephemeral signing key | Generated-key path refused in production; `SECRET_KEY` required, min 32 chars |
| **S-6** | 🟡 No request size limit | `MAX_CONTENT_LENGTH` = 64 KB → 413 before parsing |
| **D-6** | 🟠 `SECRET_KEY` not enforced in production | Startup now fails without it |

### Also fixed in this phase (not in the Phase 1 list)

| Finding | Detail |
|---|---|
| **Type confusion → 500s** | `{"name": {"$ne": null}}` and similar raised `AttributeError` and surfaced as **500** on register, login, volunteer, chatbot and recommend. All string fields now read through one `text()` helper; wrong types return **400**. A 500 is an oracle — it tells an attacker they reached unexpected code |
| **`dog_id` not coerced** | SQLite quietly returns no row for a non-numeric id, but **PostgreSQL raises** — so after the Supabase migration this would have been a 500 instead of a 404. Now coerced to `int` with a 400 on failure |
| **Error responses could leak internals** | Added a catch-all handler returning a generic message plus a session rollback; real detail goes to the server log only. Added 405/413/429 handlers |
| **`.env.production` would have been committed** | Root `.gitignore` had `.env` but not `.env.*`. Vite also reads `.env.production` / `.env.development` / `.env.local`. Now `.env.*` with an explicit `!.env.example`. **Verified with `git check-ignore` against a throwaway repo** |

### Git hygiene (item J)

No `.env`, private key, certificate, token or credential exists in the working
tree. The only files on disk that must never be committed — `.secret_key` and
`dogopaw.db` — are both correctly ignored. Nothing was deleted: the two test
artifacts removed (`prodtest.db`, `instance/`) were created by this phase's own
test runs.

### Still outstanding

Every **deployment** blocker from §9 remains, unchanged and by instruction:

- **D-1** no git repository · **D-2** no PostgreSQL driver · **D-3** no WSGI
  server · **D-4** `postgres://` not normalised · **D-5** no Vercel SPA rewrite
- **D-7** no `pool_pre_ping` · **D-8** `seed()` races across workers ·
  **D-9** no Python version pin · **D-10** `VITE_API_URL` undocumented
- **D-11…D-16** unchanged

Accepted risks (JWT in `localStorage`, per-process rate limits, chatbot question
retention, volunteer PII at rest) are documented with reasoning in
[`SECURITY.md` §12](SECURITY.md).

### Test results — Phase 3

| Suite | Checks | Result |
|---|---|---|
| Security suite (new) | 69 | ✅ **69/69** |
| API workflow suite | 77 | ✅ **77/77** — no regression |
| Recommender property tests | 16 | ✅ **16/16** |
| `api.js` error handling | 6 | ✅ **6/6** |
| Backend byte-compile + imports | 12 modules | ✅ OK |
| Frontend lint | — | ✅ clean |
| Frontend build | — | ✅ 512ms, 688.72 kB (slightly smaller — the credential panel is gone) |
| Live server: CORS, rate limiting | — | ✅ verified over real HTTP |

**168 automated checks, 0 failures.** No feature was removed or broken.

---

## 14 — Phase 4: PostgreSQL migration status

**Date:** 2026-09-20. Full detail in [`DATABASE.md`](DATABASE.md).

### Resolved

| ID | Finding | How |
|---|---|---|
| **D-2** | 🔴 No PostgreSQL driver | `psycopg[binary]==3.3.6` added — prebuilt wheels, no compiler needed on the host |
| **D-4** | 🔴 `postgres://` not normalised | `resolve_database_uri()` rewrites `postgres://` → `postgresql://` → `postgresql+psycopg://`; an explicit `+driver` is left alone |
| **D-7** | 🟠 No `pool_pre_ping` | Applied to Postgres only, with `pool_recycle=280` under Supabase's ~300 s idle cutoff |
| **D-8** | 🟠 `seed()` races across workers | `seed_lock()` — a PostgreSQL advisory lock around the whole check-then-act sequence; a no-op on SQLite |

### Also fixed in this phase

| Finding | Detail |
|---|---|
| **Column widths unenforced** | SQLite ignores `VARCHAR(n)`, PostgreSQL enforces it. `volunteers.mobile` (32), `.state`/`.city` (80) and `.email` (255) had **no** application-side cap, so a value that saved locally would have raised `DataError` → **500** on Supabase. The mobile case is the subtle one: the digit rule bounds digits, not raw length, so a 43-character number with 16 digits passed. All now validated against their exact column widths |

### Architecture

Confirmed unchanged and correct: **React → Flask API → PostgreSQL**. The
frontend has no database coupling at all — `supabase`, `postgres` and `psycopg`
appear nowhere in `app/frontend/src/` or its `package.json`.

### Still outstanding

- **D-1** no git repository · **D-3** no WSGI server · **D-5** no Vercel SPA
  rewrite · **D-9** no Python version pin · **D-10** `VITE_API_URL` undocumented
- **D-11…D-16** unchanged

### Test results — Phase 4

| Suite | Checks | Result |
|---|---|---|
| PostgreSQL compatibility (new) | 41 | ✅ **41/41** |
| `verify_db.py` (new) on SQLite | 31 | ✅ **31/31** |
| Security suite | 69 | ✅ **69/69** — no regression |
| API workflow suite | 77 | ✅ **77/77** — no regression |
| Recommender property tests | 16 | ✅ **16/16** |
| Frontend lint / build | — | ✅ clean / 4.52s |

**234 automated checks, 0 failures.**

> ⚠️ **A live Supabase connection was not tested.** No PostgreSQL server or
> Docker was available in this environment and no credentials were provided —
> so that result is not claimed. `verify_db.py` plus the exact commands to run
> it are in [`DATABASE.md` §10](DATABASE.md).

---

## 15 — Phase 5: backend deployment preparation status

**Date:** 2026-09-20. Full detail in [`DEPLOYMENT_BACKEND.md`](DEPLOYMENT_BACKEND.md).
**Nothing has been deployed.**

### Resolved

| ID | Finding | How |
|---|---|---|
| **D-3** | 🔴 No WSGI server | `gunicorn==26.2.0` added, with `gunicorn.conf.py`. Start command `gunicorn app:app`; `app:app` verified as a Flask instance and WSGI callable |
| **D-9** | 🟠 No Python version pin | `3.13.7` pinned in both `.python-version` and `render.yaml`. Linux wheels verified for every compiled dependency on cp313 **and** cp314 |
| **D-13** | 🟡 Render cold start | Documented with expected ~50 s, plus the "open the site a minute before the viva" mitigation |

### Also found in this phase

| Finding | Detail |
|---|---|
| **Gunicorn's default worker count would OOM the instance on boot** | Measured: one worker is **~158 MB**; the free tier is **512 MB**. Gunicorn defaults to `(2 × CPU) + 1`, and a Render free instance reports the *host* CPU count rather than its 0.1 CPU share — so the default is 17+ workers, ~2.7 GB, OOM-killed before serving a request. Pinned to **2 workers (~317 MB)** with 4 threads. The symptom ("deploy succeeded, service won't start") does not point at the cause, so this would have been a genuinely hard failure to diagnose |

### Verified by running, not by assertion

The WSGI object was served over **real HTTP under `APP_ENV=production`**:
`/api/health` → 200, `/api/dogs` → 18, CORS allowed the configured origin and
refused others, admin logged in with `ADMIN_PASSWORD`, the **dev password was
rejected (401)**, the **demo account was absent (401)**, and
`/api/admin/stats` returned 401 unauthenticated.

Also confirmed: the app runs correctly from **any** working directory (all paths
are `__file__`-relative), there are no Windows paths or drive letters in source,
and the health endpoint touches no database — so a Supabase blip cannot trigger
a Render restart loop.

### Not verified — stated, not glossed

| Not tested | Why |
|---|---|
| Gunicorn actually running | Does not run on Windows. Config validated; the same WSGI object was served via `wsgiref` instead |
| Python 3.13 runtime | Only 3.14.3 is installed locally. Dependencies pinned exactly and pickles are protocol 5, so the risk is low but not zero |
| Live Supabase connection | No credentials available — see [`DATABASE.md`](DATABASE.md) §10 |
| Render itself | Nothing deployed; that is Phase 7 |

### Still outstanding

- **D-1** no git repository · **D-5** no Vercel SPA rewrite ·
  **D-10** `VITE_API_URL` undocumented · **D-11** README ·
  **D-12** 29.9 MB video · **D-14** 689 kB chunk · **D-16** no CI

### Test results — Phase 5

| Suite | Result |
|---|---|
| Recommender (16) · Workflow (77) · Security (69) · PG compat (41) · `verify_db` (31) · `api.js` (6) | ✅ **all pass, no regression** |
| Byte-compile + imports (13 modules + gunicorn config) | ✅ OK |
| Frontend lint / build | ✅ clean / 1.13s |

**240 automated checks, 0 failures.**

---

## 16 — Phase 6: frontend deployment preparation status

**Date:** 2026-09-20. Full detail in [`DEPLOYMENT_FRONTEND.md`](DEPLOYMENT_FRONTEND.md).
**Nothing has been deployed.**

### Resolved

| ID | Finding | How |
|---|---|---|
| **D-5** | 🔴 No Vercel SPA rewrite | `app/frontend/vercel.json` with a catch-all rewrite, plus cache and security headers. **Verified against the real `dist/`** with Vercel's filesystem-first ordering simulated |
| **D-10** | 🟠 `VITE_API_URL` undocumented | `app/frontend/.env.example` added and documented, including that `VITE_`-prefixed values are public |
| **D-15** | 🟢 "port 5001" in production error copy | The offline message now differs by environment; the dev text is stripped from production builds |

### Also fixed in this phase

| Finding | Detail |
|---|---|
| **Every route shared one `<title>`** | A single-page app never reloads, so every tab, bookmark and history entry read "Dogo-Paw — Rescue, Foster, Adopt" — including a specific dog's page. `Layout.jsx` now sets a per-route title in the effect that already handled scroll restoration. Kept in one place deliberately: two components writing `document.title` would race on effect ordering |
| **No sharing metadata** | Open Graph and Twitter card tags added, plus `theme-color` and `robots.txt`. `og:image` is site-relative, so the deployment domain stays out of the source |
| **Trailing slash in `VITE_API_URL`** | `https://api.example.com/` would have built `https://api.example.com//api/dogs`. The value is pasted by hand into a dashboard, so trailing slashes are now stripped |

### The collision worth knowing about

`/dogs` is **both a route and a folder of real files** — the gallery is at
`/dogs`, and each photo is served from `public/dogs/dog-01.jpg`. A catch-all SPA
rewrite looks like it would swallow the images.

It does not: Vercel checks the filesystem *before* applying rewrites. Verified
empirically against the real build — `/dogs/3` returns the SPA shell while
`/dogs/dog-01.jpg` is served as `image/jpeg`.

An earlier draft used a negative-lookahead pattern to exclude `/assets/`. It was
removed as unnecessary complexity that covered only one of the three asset
folders.

### Audited, no change needed

- **Mobile responsiveness** — viewport meta present, 197 responsive class
  prefixes, a 20 px mobile gutter, and no fixed widths that force horizontal
  scroll. The two hard pixel numbers are both correct (`max-w-[220px]` is a
  maximum; `min-w-[720px]` is a table inside `overflow-x-auto`).
- **API surface** — exactly **one** `fetch` in the whole frontend, in
  `lib/api.js`. No hardcoded backend or localhost URLs.
- **Debug output** — no `console.log`, `debugger` or `alert` in source or bundle.
- **Demo credentials** — absent from the production bundle (Phase 3), re-confirmed.
- **No UI or design changes were made.**

### Still outstanding

- **D-1** no git repository · **D-11** README ·
  **D-12** 29 MB video (83% of the 35 MB repo) · **D-14** 689 kB chunk ·
  **D-16** no CI

### Test results — Phase 6

| Suite | Checks | Result |
|---|---|---|
| `api.js` URL construction (new) | 9 | ✅ **9/9** |
| SPA routing vs real `dist/` (new) | 13 paths | ✅ **13/13** |
| `api.js` error handling | 6 | ✅ **6/6** |
| Frontend lint / production build | — | ✅ clean / 1.23s |
| Backend: recommender, workflow, security, PG compat, `verify_db` | 234 | ✅ **no regression** |

**262 automated checks, 0 failures.**

---

## 17 — Phase 7: public-facing and privacy readiness

**Date:** 2026-09-20. Full detail in
[`PRIVACY_DATA_HANDLING.md`](PRIVACY_DATA_HANDLING.md).
**No redesign — text, links and notices only.**

### The two things that actually needed fixing

| Finding | Detail |
|---|---|
| **No synthetic-data disclosure anywhere in the UI** | The 18 dogs are a synthetic dataset and the photos are reused crops, but the only hint to a visitor was a small "Representative photo" caption. The site read as a live adoption listing — and the dog profile page has a **"Call about &lt;name&gt;" button dialling a real phone number** about an animal that does not exist. Now disclosed in four places: `/dogs`, `/dogs/:id` (above the name, before the call-to-action), `/adopt-match`, and the footer on every route |
| **No privacy notice, on a form collecting a home address** | `/volunteer` collects name, email, phone, **full address**, state and city, with **zero** privacy text anywhere in the app. A notice now sits directly above the submit button — before someone hands the details over, not behind a link |

### Broken and placeholder links

| Item | Was | Now |
|---|---|---|
| WhatsApp | `https://wa.me/` — **genuinely broken**; the URL requires a phone number, a bare one is an error page | Not rendered |
| Instagram | `https://instagram.com/` — the site's home page, not an account | Not rendered |
| Facebook | `https://facebook.com/` — same | Not rendered |

The list is now data-driven: an entry renders only when `href` is set, and the
"Follow along" block hides itself when none are. **No accounts were invented** —
the comment in `Footer.jsx` gives the exact URL format to fill in.

### Overstated claims removed

| Was | Why it went |
|---|---|
| "Adoption enquiries answered within 48 hours" (footer) | A response-time promise with no staffed inbox behind it |
| "We usually respond within 48 hours" (volunteer page) | Same — replaced with "A volunteer coordinator will get back to you" |
| "© Dogo-Paw Rescue. All rights reserved." | Implied a registered organisation. Now "© Dogo-Paw. Student project." |

### Audited, already correct

- **Alt text — 11/11 images.** Decorative images correctly use `alt=""`.
- **Accessibility** — `aria-label` ×18, `aria-hidden` ×29, `role` ×14,
  `aria-invalid`/`aria-describedby` wired on both forms, `sr-only` ×4,
  `focus-visible` styling. **Added** the one missing basic: a skip-to-content link.
- **Loading, empty and error states** — all three present and specific
  (`Spinner` has `role="status"`; the gallery has a real empty state with a
  reset action; errors use `role="alert"`).
- **404 page** — exists, on-brand, with a route home.
- **No invented statistics** anywhere. The only numbers are "18 dogs", which is
  accurate. No lorem ipsum, no TODO/TBD markers.
- **About page** makes **no** false registration, charity, tax-status or address
  claims — nothing needed correcting.
- **Mobile layout** — unchanged from the Phase 6 audit; no regressions.

### Flagged for your decision — deliberately NOT changed

| Detail | Where | Concern |
|---|---|---|
| `+91 70155 96198` | Footer, **and the "Call about &lt;dog&gt;" button on all 18 profiles** | If this is a real personal mobile, publishing it invites calls from strangers about dogs that do not exist |
| `hello@dogo-paw.org` | Footer | The domain does not appear to be owned by this project, so mail to it will not arrive |

These are real-world identity decisions, not code decisions. No replacement was
invented.

### Test results — Phase 7

| Suite | Checks | Result |
|---|---|---|
| Rendered-HTML disclosure & privacy checks (new) | 16 | ✅ **16/16** |
| Frontend lint | — | ✅ clean |
| Frontend build | — | ✅ 1.38s, 691.54 kB (+2.4 kB for the notices) |
| Bundle content verification | — | ✅ disclosures in, placeholder links out |
| Dependencies added | — | **none** |

---

## 18 — Phase 8: end-to-end QA

**Date:** 2026-09-20. Full report in [`TEST_REPORT.md`](TEST_REPORT.md).

**112 tests executed · 112 PASS · 0 FAIL · 0 BLOCKED · 0 application bugs found.**

All 50 required test areas were genuinely executed — nothing was marked PASS on
inspection alone. A full stack was stood up: the real Flask backend over HTTP,
the **production** frontend build served with Vercel's routing order, and
**headless Chromium** driving it at desktop and mobile sizes, with real
cross-origin requests so CORS actually applied.

Playwright and Chromium live outside the project; **`package.json` and
`requirements.txt` are unchanged**.

### Three first-run failures — all test-harness defects, not application bugs

| Test | Root cause | Application change |
|---|---|---|
| 8 — matcher returns results | The questionnaire's radios are `sr-only` with the visible `<label>` as the control (a correct accessible pattern). The harness tried to click the input; Playwright rightly refused because the label intercepts. The form was never filled | **None** — harness now clicks the label |
| 8.1 — results carry the disclosure | Same cause; results never rendered | **None** |
| 11 — chatbot answers | The toggle's accessible name is "Open the help assistant"; the selector looked for "chat" | **None** — selector corrected |

Each was diagnosed by dumping the live DOM **before** changing anything, which
is what confirmed the markup was correct. No critical or high-severity issue was
found, so the instruction to fix such issues went unused — not skipped.

### Notable confirmations

- **Mobile 375px: zero horizontal overflow across all 8 public routes**, and no
  tap target under 24px.
- **Refresh on `/dogs/5` works** and `/dogs/dog-01.jpg` is still served as an
  image — the SPA rewrite does not shadow the photos.
- **CORS verified over real cross-origin HTTP**, not just from config.
- Login errors are identical for a wrong email and a wrong password, so the
  endpoint is not a user-enumeration oracle.
- Expired, revoked, tampered and `alg:none` tokens are all refused.
- The admin dashboard renders fully — charts, segments, FAQ activity — **with no
  JS errors**.
- With the API unreachable, the site shows a readable message using the
  **production** copy, with no "port 5001".

### Still outstanding

- **D-1** no git repository · **D-11** README ·
  **D-12** 29 MB video · **D-14** 689 kB chunk · **D-16** no CI
- **Live Supabase, Render and Vercel remain untested** — the main remaining
  unknown, and the reason [`TEST_REPORT.md`](TEST_REPORT.md) §11 lists what this
  QA did not cover.

---

## Appendix A — Files inspected

**Configuration and documentation (8)**
`.gitignore`, `README.md`, `app/README.md`, `app/backend/.gitignore`,
`app/backend/.env.example`, `app/backend/requirements.txt`,
`app/frontend/package.json`, `app/frontend/.oxlintrc.json`

**Backend Python (13)**
`app.py`, `models.py`, `auth.py`, `recommender.py`, `seed.py`, `demo_data.py`,
`clean_test_data.py`, `test_recommender.py`, `ml/__init__.py`, `ml/features.py`,
`ml/success_model.py`, `ml/segmentation.py`, `ml/chatbot.py`

**ML artifacts (3)**
`ml/artifacts/success_model.joblib`, `ml/artifacts/chatbot_model.joblib`,
`ml/artifacts/success_model_coefficients.json`

**Frontend (read in full — 11)**
`vite.config.js`, `index.html`, `src/main.jsx`, `src/App.jsx`, `src/lib/api.js`,
`src/lib/matchSession.js`, `src/context/AuthContext.jsx`,
`src/context/auth-context.js`, `src/context/useAuth.js`,
`src/components/ProtectedRoute.jsx`, `src/pages/Login.jsx` (demo-credential block)

**Frontend (surveyed — structure, API usage, env/storage access — 17)**
All 11 `src/pages/*.jsx`, `src/components/ChatWidget.jsx`,
`src/components/VolunteerForm.jsx`, `src/components/charts.jsx`,
`src/lib/dogs.js`, `src/assets/images.js`, `scripts/*.mjs`

**Total: 52 files inspected.**

## Appendix B — Commands executed

```bash
# Inspection
find / ls / wc / grep / du            # structure, sizes, secret + pattern scans
git rev-parse --is-inside-work-tree   # → "not a git repository"

# Frontend
npm install                           # exit 0
npm run lint                          # oxlint — clean
npm run build                         # built in 6.80s
npm audit --omit=dev                  # 0 vulnerabilities

# Backend
python -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m compileall -q .          # OK
.venv/Scripts/python.exe test_recommender.py         # ALL CHECKS PASSED
.venv/Scripts/python.exe -c "<import all 11 modules>"      # 11/11 OK
.venv/Scripts/python.exe -c "<14-endpoint smoke test>"     # 14/14 correct
.venv/Scripts/python.exe -c "<8 auth/authz path tests>"    # 8/8 correct
.venv/Scripts/python.exe -c "<ML artifact load + metrics>" # all match README
```

**Environment:** Windows 11, Node v22.20.0, npm 10.9.3, Python 3.14.3.
Nothing failed to execute for environment reasons. All pinned Python
dependencies had wheels available for Python 3.14.

**Side effects of the audit** (all gitignored, all regenerable, no source
modified): `app/frontend/node_modules/`, `app/frontend/dist/`,
`app/backend/.venv/`, `app/backend/__pycache__/`, `app/backend/dogopaw.db`
(created and seeded), `app/backend/.secret_key` (generated). The smoke tests
wrote a small number of rows to the local database — removable with
`python clean_test_data.py --apply` or `python demo_data.py --clear`.

## Appendix C — Required environment variables

| Variable | Side | Required in production | Current default | Notes |
|---|---|---|---|---|
| `SECRET_KEY` | backend | **Yes** | generated to `.secret_key` | Must be set on Render or all sessions break on restart |
| `DATABASE_URL` | backend | **Yes** | `sqlite:///dogopaw.db` | Supabase URI; needs scheme normalisation (D-4) |
| `CORS_ORIGINS` | backend | **Yes** | `*` | Must be pinned to the Vercel domain |
| `PORT` | backend | provided by Render | `5001` | Render injects this |
| `VITE_API_URL` | frontend | **Yes** | `''` (dev proxy) | Build-time; must be set in Vercel before the build |
| `ADMIN_PASSWORD` | backend | **proposed** | — | Does not exist yet; proposed fix for S-1 |
