# Dogo-Paw — Production Deployment

The deployment procedure, the architecture it produces, and how to verify,
health-check and roll it back.

**Status:** prepared and committed — **not yet deployed.** Every item in §1 that
requires a hosting account is yours to perform; this document is the procedure
and the verification for each step.

> **No secret values appear in this document.** Only variable *names* and where
> they are set.

---

## 1. Pre-deployment checklist

| # | Item | Status | Where |
|---|---|---|---|
| 1 | **Git repository** | ✅ initialised, 129 files committed on `main`. **Not pushed** — needs your GitHub account | local |
| 2 | **Production environment variables** | ✅ defined and enforced at startup | §4, §6 |
| 3 | **Supabase database** | ⬜ **you create it** | §3 |
| 4 | **Render backend** | ⬜ **you create it** | §4 |
| 5 | **Gunicorn configuration** | ✅ `app/backend/gunicorn.conf.py`, 2 workers × 4 threads | §4 |
| 6 | **Vercel frontend** | ⬜ **you create it** | §6 |
| 7 | **`VITE_API_URL`** | ✅ code reads it; value set in Vercel | §6 |
| 8 | **`CORS_ORIGINS`** | ✅ wildcard refused in production; value set in Render | §7 |
| 9 | **`SECRET_KEY`** | ✅ required in production; Render generates it | §4 |
| 10 | **Database initialization** | ✅ automatic and idempotent, under an advisory lock | §3 |
| 11 | **ML model availability** | ✅ 3 artifacts committed (466 KB); no training on the server | verified in the commit |
| 12 | **SPA routing** | ✅ `app/frontend/vercel.json` catch-all rewrite | §6 |
| 13 | **HTTPS** | ✅ provided and enforced by both platforms | §8 |
| 14 | **Health check** | ✅ `/api/health`, touches no database | §4 |

### What must be true before you start

- A GitHub account, and Supabase / Render / Vercel accounts (all have free tiers).
- The repository pushed to GitHub — **both platforms deploy from git**.

---

## 2. Target architecture

```
                    ┌──────────────────────────┐
   visitor ───────▶ │  Vercel                  │   React 19 + Vite
                    │  static build (dist/)    │   SPA rewrite → index.html
                    └────────────┬─────────────┘
                                 │  HTTPS, cross-origin
                                 │  Authorization: Bearer <JWT>
                                 ▼
                    ┌──────────────────────────┐
                    │  Render                  │   Flask 3 + gunicorn
                    │  gunicorn app:app        │   2 workers × 4 threads
                    │  rootDir app/backend     │   ML models loaded at boot
                    └────────────┬─────────────┘
                                 │  TLS, sslmode=require
                                 │  session pooler :5432
                                 ▼
                    ┌──────────────────────────┐
                    │  Supabase PostgreSQL     │   7 tables
                    └──────────────────────────┘
```

**The browser never reaches the database.** There is no database client or
credential in the frontend. Unchanged from the original architecture.

---

## 3. Step 1 — Supabase (database first)

The database has no dependencies, so it goes first.

1. [supabase.com](https://supabase.com) → **New project**. Choose a region near
   you and set a database password — **it is shown once**.
2. Wait for provisioning (~2 minutes).
3. **Project Settings → Database → Connection string → Session Pooler**.
   Copy the URI. It ends in port **5432**.
4. Substitute your database password for the `[YOUR-PASSWORD]` placeholder, and
   make sure it ends with `?sslmode=require`.

Use the **Session Pooler (port 5432 on the `…pooler.supabase.com` host)**, not
the direct connection (`db.PROJECT_REF.supabase.co`): Render runs several
workers and restarts often, which exhausts the direct connection limit.

On the pooler host the port selects the mode — **5432 is the Session Pooler**
and 6543 is the Transaction Pooler. Session mode is required here, because
Alembic migrations and psycopg's prepared statements both need a connection
that outlives a single transaction.

### ✅ Verify before continuing

```bash
cd app/backend
# PowerShell: $env:DATABASE_URL="..."   bash: export DATABASE_URL="..."
python verify_db.py
```

**Expect:** `ALL DATABASE CHECKS PASSED on postgresql`, 31/31.

Two lines will read differently than on SQLite — `[rejected]` instead of
`[not enforced by SQLite]`. **That difference is your proof you are really on
PostgreSQL**, because those constraints are enforced there and ignored by SQLite.

If it fails, the symptom table in [`DATABASE.md`](DATABASE.md) §10 names the
cause.

> The tables do not exist yet — that is expected. The app creates and seeds them
> on its first boot in §4.

---

## 4. Step 2 — Render (backend)

### Push to GitHub first

```bash
cd "D:/Dogo-Paw ITR"
git remote add origin https://github.com/<you>/dogo-paw.git
git push -u origin main
```

The push moves ~35 MB and will take a minute — 29 MB of that is the hero video.

### Create the service

[`render.yaml`](../render.yaml) is committed, so **New → Blueprint** reads it
and prompts only for the secrets. Otherwise, **New → Web Service**:

| Field | Value |
|---|---|
| Runtime | Python 3 |
| **Root Directory** | **`app/backend`** |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app` |
| Health Check Path | `/api/health` |
| Instance Type | Free |

**Root Directory is the one that is easy to miss.** The backend's modules are
top-level imports, so gunicorn must start inside `app/backend` or it fails with
`ModuleNotFoundError: No module named 'app'`.

### Environment variables

| Name | Value | Notes |
|---|---|---|
| `APP_ENV` | `production` | **The most important line.** Without it the app runs with development defaults |
| `PYTHON_VERSION` | `3.13.7` | |
| `SECRET_KEY` | *Render generates* | Use "Generate" — it stays stable across deploys |
| `DATABASE_URL` | *your Supabase pooler URI* | From §3 |
| `ADMIN_PASSWORD` | *your choice, 12+ characters* | The seeded admin's password |
| `CORS_ORIGINS` | `https://placeholder.vercel.app` | **Temporary** — corrected in §7 |
| `WEB_CONCURRENCY` | `2` | Leave at 2 on the free tier |

`CORS_ORIGINS` is circular — the frontend does not exist yet. Set a placeholder
now; §7 fixes it. It must not be empty or `*`, or the app refuses to start.

### What happens on first boot

The app creates all 7 tables, inserts the 18 dogs and creates the admin account —
automatically, idempotently, and under a PostgreSQL advisory lock so concurrent
workers cannot race. **No release command or migration step is needed.**

In production the **demo adopter is not created**, and the admin password comes
from `ADMIN_PASSWORD`.

### ✅ Verify before continuing

```bash
curl https://YOUR-APP.onrender.com/api/health
```

**Expect:** `{"status":"ok","time":"..."}`

The first request may take **~50 seconds** while the instance wakes. That is
normal on the free tier, not a failure.

Then run the full backend verification:

```bash
cd app/backend
# PowerShell: $env:ADMIN_PASSWORD="your-admin-password"
python verify_deployment.py https://YOUR-APP.onrender.com
```

This performs every check you asked for — health, register → login → logout →
**login again** (proving persistence), the questionnaire, the volunteer form,
the chatbot, and admin authorization.

**Expect:** `DEPLOYMENT VERIFIED`, with CORS and frontend checks skipped until §7.

Two checks specifically catch a misconfigured deployment:

- *"the DEVELOPMENT admin password does NOT work in production"*
- *"the demo account was NOT seeded in production"*

**If either fails, `APP_ENV` is not set to `production`.** Fix that before going
further — those are the credentials that used to be printed on the login page.

**Also check Render's Logs tab.** A healthy boot shows:

```
database: postgresql (production)
loaded success predictor
loaded intent classifier
[INFO] Booting worker with pid: ...
[INFO] Booting worker with pid: ...
```

`database: sqlite` means `DATABASE_URL` did not take effect. A missing
"loaded ..." line means an ML artifact did not deploy.

---

## 5. Step 3 — Supabase data check

With the backend live, confirm the data really landed.

Supabase → **Table Editor**. Expect:

| Table | Expected |
|---|---|
| `dogs` | **18 rows** |
| `users` | **1 row** — the admin only (the demo adopter is correctly absent) |
| `volunteers`, `adopters`, `match_requests`, `chatbot_logs` | rows from the verification run above |
| `revoked_tokens` | at least one, from the logout check |

Seeing the `verify_deployment.py` rows here is the database persistence proof:
they were written through the API, over the internet, into PostgreSQL.

---

## 6. Step 4 — Vercel (frontend)

1. [vercel.com](https://vercel.com) → **Add New → Project** → import the repository.
2. Configure:

| Field | Value |
|---|---|
| Framework Preset | **Vite** (auto-detected) |
| **Root Directory** | **`app/frontend`** |
| Build Command | `npm run build` *(default)* |
| Output Directory | `dist` *(default)* |

3. Environment variable:

| Name | Value |
|---|---|
| `VITE_API_URL` | `https://YOUR-APP.onrender.com` — **no trailing slash, no path** |

Apply it to **Production**, **Preview** and **Development**.

4. **Deploy.**

> `VITE_API_URL` is baked into the bundle **at build time**, not read at runtime.
> Changing it later requires a **rebuild**, not just a restart.

`vercel.json` is already committed at `app/frontend/`, so the SPA rewrite and the
cache/security headers apply automatically.

### ✅ Verify before continuing

```bash
curl -I https://YOUR-APP.vercel.app            # 200
curl -I https://YOUR-APP.vercel.app/dogs/3     # 200, NOT 404
```

A 404 on `/dogs/3` means `vercel.json` was not picked up — check the Root
Directory setting.

---

## 7. Step 5 — Close the CORS loop

The two services must now know about each other.

**Render → Environment →** set `CORS_ORIGINS` to your real Vercel URL:

```
CORS_ORIGINS = https://YOUR-APP.vercel.app
```

Exact match: `https://`, no trailing slash. Saving restarts the service (~1 min).

### ✅ Verify the whole system

```bash
cd app/backend
python verify_deployment.py https://YOUR-APP.onrender.com https://YOUR-APP.vercel.app
```

**Expect:** `DEPLOYMENT VERIFIED` with nothing skipped — now including CORS,
deep links, static images and HTTPS.

---

## 8. Step 6 — Manual verification in a browser

The script covers the API. This covers what a visitor actually experiences.

| # | Check | Expected |
|---|---|---|
| 1 | Open the Vercel URL | Home page with the hero video |
| 2 | `/dogs` | **18 dogs with photos** — proves API + static images |
| 3 | Filter by size, search "Luna" | List narrows instantly |
| 4 | Open a dog | Profile, bio, **demonstration-data notice** |
| 5 | **Refresh that page** | Still renders — **not a 404** |
| 6 | `/adopt-match`, answer 5 questions | 18 ranked matches with explanations |
| 7 | Chat widget → "how do I foster?" | A relevant answer |
| 8 | `/volunteer` | **Privacy notice visible**; submit succeeds |
| 9 | `/login` | **No demo credentials shown** |
| 10 | Register → Logout → **Login again** | Account persisted |
| 11 | `/admin` as that user | "Admin access only", **no data** |
| 12 | `/admin` as admin | Dashboard with charts, segments, FAQ activity |
| 13 | A nonsense URL | 404 page with a route home |
| 14 | Open on a phone | No horizontal scrolling |

Cross-check in Supabase's Table Editor that your registration and volunteer
submission appear in `users` and `volunteers`.

---

## 9. Environment variables (names only)

### Render (backend)

| Name | Required | Set by |
|---|---|---|
| `APP_ENV` | **yes** | you — `production` |
| `SECRET_KEY` | **yes** | Render generates |
| `DATABASE_URL` | **yes** | you — Supabase pooler URI |
| `ADMIN_PASSWORD` | **yes** | you — 12+ characters |
| `CORS_ORIGINS` | **yes** | you — the Vercel URL |
| `PYTHON_VERSION` | yes | `3.13.7` |
| `WEB_CONCURRENCY` | recommended | `2` |
| `PORT` | no | injected by Render |

### Vercel (frontend)

| Name | Required | Value |
|---|---|---|
| `VITE_API_URL` | **yes** | the Render URL |

**In production the backend refuses to start** without `SECRET_KEY`,
`CORS_ORIGINS` and `ADMIN_PASSWORD`, or with `CORS_ORIGINS='*'`. A deployment
that fails loudly at boot is far safer than one that runs misconfigured.

> `VITE_API_URL` is compiled into the public JavaScript bundle. That is correct —
> it is a public endpoint. **Never give a secret a `VITE_` prefix.**

---

## 10. Health-check procedure

### Automatic

Render polls `/api/health` and restarts the service if it stops returning 2xx.
The endpoint touches **no database**, so a brief Supabase blip cannot cause a
restart loop.

### Manual — 10 seconds

```bash
curl https://YOUR-APP.onrender.com/api/health
curl -I https://YOUR-APP.vercel.app
```

### Full — 2 minutes

```bash
cd app/backend
python verify_deployment.py https://YOUR-APP.onrender.com https://YOUR-APP.vercel.app
```

Run this after **every** change to either service.

### Before a demo or viva

**Open the site a minute beforehand.** The free instance sleeps after ~15 minutes
idle and takes ~50 s to wake; a cold start mid-demo looks like a broken
deployment.

---

## 11. Rollback procedure

### Frontend (Vercel) — instant

Vercel keeps every deployment. **Deployments → pick the last good one →
Promote to Production.** Takes seconds, no rebuild.

### Backend (Render) — a few minutes

**Events/Deploys → pick the last good deploy → Redeploy**, or revert in git:

```bash
git revert <bad-commit>
git push          # Render redeploys automatically
```

### Environment variable mistake

Correct the value in the dashboard. Render restarts on save (~1 min). For
`VITE_API_URL`, **redeploy Vercel** — it is baked in at build time.

### Database

⚠️ **Code rollbacks do not roll back data.** Supabase free keeps **daily backups
with 7-day retention** (Database → Backups). Take your own dump before anything
risky:

```bash
pg_dump "$DATABASE_URL" > backup-$(date +%F).sql
```

`volunteers` and `users` are the only tables holding data you cannot recreate —
see [`DATABASE.md`](DATABASE.md) §9.

### Total rollback

Both platforms let you delete and recreate a service from the same repository.
Nothing except the database is stateful, so a full rebuild is safe — as long as
`DATABASE_URL` still points at the same Supabase project.

---

## 12. Known free-tier behaviour

| Behaviour | Detail |
|---|---|
| **Cold starts** | Backend sleeps after ~15 min idle; first request ~50 s. The frontend shows "Could not reach the server... it may be waking up" |
| **Rate limits reset on restart** | They live in memory |
| **Per-worker limits** | 2 workers means the effective limit is up to 2× the configured one |
| **Ephemeral disk** | Nothing written to disk survives — which is why `SECRET_KEY` must be an environment variable |
| **Supabase backups** | Daily, 7-day retention |

None of these is a defect; all are documented free-tier trade-offs.

---

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Build succeeds, service never starts | Too many gunicorn workers → OOM | `WEB_CONCURRENCY=2` |
| `ModuleNotFoundError: No module named 'app'` | Root Directory not set | Set it to `app/backend` |
| `SECRET_KEY must be set...` | Missing variable | Add it |
| `CORS_ORIGINS='*' is not allowed` | Wildcard in production | Set the exact Vercel origin |
| Site loads, **every API call fails** | `CORS_ORIGINS` mismatch | Must match exactly — `https://`, no trailing slash |
| `admin123` still works | `APP_ENV` is not `production` | **Fix immediately** |
| `Can't load plugin: ...postgres` | URL bypassed normalisation | Use the app's config path |
| `too many connections` | Direct connection (`db.PROJECT_REF.supabase.co`) | Use the Session Pooler host on port 5432 |
| `/dogs/3` returns 404 | `vercel.json` not applied | Check Vercel's Root Directory |
| `/api/model-info` → 503 | ML artifacts missing | Confirm `ml/artifacts/*.joblib` are committed |
| First request very slow | Cold start | Normal — wait ~50 s |

---

## 14. After deployment — record these

Fill in once deployed. **URLs only, never secret values.**

| | |
|---|---|
| Frontend URL | `https://__________.vercel.app` |
| Backend URL | `https://__________.onrender.com` |
| Supabase project | `__________` |
| GitHub repository | `https://github.com/__________` |
| Deployed on | `__________` |
| Admin email | `admin@dogo-paw.org` |
| Admin password | **stored in Render only — never written down here** |

---

## 15. Public-facing details you chose to keep

Raised during the Phase 7 review and **kept at your instruction**:

| Detail | Where | Note |
|---|---|---|
| `+91 70155 96198` | Footer, and the "Call about &lt;dog&gt;" button on all 18 dog profiles | Kept as-is. It is publicly visible once deployed, and the dog profiles are demonstration data — so a caller may be asking about an animal that does not exist. The demonstration-data notice sits directly above that button on every profile |
| `hello@dogo-paw.org` | Footer | The domain does not appear to be registered to this project, so mail sent to it will not arrive |

Neither blocks deployment. Both are recorded so the decision is visible rather
than forgotten.
