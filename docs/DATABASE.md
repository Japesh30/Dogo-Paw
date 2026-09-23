# Dogo-Paw — Database

How data is stored, how the two environments differ, and how to set up,
verify, upgrade and back up the production database.

**Applies from:** Phase 4 (PostgreSQL migration), 2026-09-20.

---

## 1. The short version

| | Development | Production |
|---|---|---|
| Engine | **SQLite** — one file | **PostgreSQL** — Supabase |
| Location | `app/backend/dogopaw.db` | Supabase project, Session Pooler on port **5432** |
| Configured by | nothing — it is the default | `DATABASE_URL` |
| Driver | built into Python | `psycopg` 3 |
| Created by | `seed()` on first run | `seed()` on first boot, under an advisory lock |
| Demo accounts | admin + demo adopter | **admin only**, password from `ADMIN_PASSWORD` |
| Committed to git? | **No** — `*.db` is ignored | n/a |

**One application, one ORM, two backends.** The same SQLAlchemy models drive
both; nothing in the application knows which engine it is talking to. Switching
is entirely a matter of `DATABASE_URL`.

```
React (Vercel)  ──HTTPS──▶  Flask API (Render)  ──TLS──▶  PostgreSQL (Supabase)
```

The browser never talks to the database. There is no Supabase client, no
connection string and no database credential anywhere in the frontend — the API
is the only thing holding them. *Verified: `supabase`, `postgres` and `psycopg`
appear nowhere in `app/frontend/src/` or its `package.json`.*

---

## 2. Development database

SQLite, kept because it is genuinely useful rather than out of habit:

- No server to install, start or keep running.
- The whole database is one file — delete it to start over.
- `python app.py` works on a fresh clone with no configuration at all.

It is created and seeded automatically on first run: 18 dogs, their bios and
photos, an admin account and a demo adopter.

```bash
cd app/backend
python app.py            # creates dogopaw.db if missing, then seeds it
```

To start over, delete the file and run again:

```bash
rm app/backend/dogopaw.db      # Windows: del app\backend\dogopaw.db
python app.py
```

`dogopaw.db` is gitignored and must never be committed — it would carry one
machine's test data, and its accounts, into every clone.

### Where SQLite and PostgreSQL genuinely differ

Three differences matter, and all three are handled:

| Difference | Consequence | How it is handled |
|---|---|---|
| **SQLite ignores `VARCHAR(n)` lengths; PostgreSQL enforces them** | An over-long value stored fine locally and raised `DataError` → **500** in production | The API validates every field against its column's exact width — see §7 |
| **SQLite does not enforce foreign keys by default; PostgreSQL always does** | A dangling reference was silently accepted locally | The delete order in `demo_data.py` and `clean_test_data.py` is child-before-parent, which is correct on both |
| **SQLite has no non-numeric id error; PostgreSQL raises** | `dog_id: "abc"` was a 404 locally and a **500** in production | `dog_id` is coerced to `int` with a 400 on failure |

This is the honest reason a "just change the URL" migration is not quite that:
the two engines disagree about how strict to be, and the application has to be
the strict one so both behave the same.

---

## 3. Production database — Supabase PostgreSQL

### Getting the connection string

1. Supabase dashboard → your project → **Project Settings → Database**.
2. Under **Connection string**, choose the **Session Pooler** — port **5432**.
3. Copy it and substitute your database password.

```
postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require
```

**Which port, and why it matters.** On the pooler host
(`…pooler.supabase.com`) the port chooses the pooling mode:

| Port | Mode | Use it here? |
|---|---|---|
| **5432** | **Session Pooler** | **Yes** — this is what production uses |
| 6543 | Transaction Pooler | No |

Session mode keeps one server connection for the life of the client session,
which is what Alembic migrations and psycopg's prepared statements need.
Transaction mode returns the connection after every statement, which breaks
both. The *direct* connection also uses 5432, but on a different host
(`db.PROJECT_REF.supabase.co`) — the host is what tells them apart.

**Use the pooler.** Render's free tier restarts often and gunicorn runs several
workers; the direct connection has a low connection ceiling that this exhausts.
The pooler exists for exactly this shape of deployment.

**Keep `?sslmode=require`.** Without it the driver may negotiate an unencrypted
connection, putting the database password and every row on the wire in clear.

> **Never commit this string.** It contains the database password. It belongs in
> Render's environment settings and nowhere else. `.env` and `.env.*` are
> gitignored; see [`SECURITY.md`](SECURITY.md).

### URL normalisation — why the app rewrites what you paste

`resolve_database_uri()` in `app.py` applies two rewrites, both necessary:

| You provide | Becomes | Why |
|---|---|---|
| `postgres://…` | `postgresql+psycopg://…` | Supabase, Render and Heroku all hand out the short form. **SQLAlchemy 2 removed it** and raises `Can't load plugin` rather than guessing |
| `postgresql://…` | `postgresql+psycopg://…` | With no driver named, SQLAlchemy reaches for **psycopg2**, which this project does not install. It uses psycopg 3 |
| `postgresql+psycopg2://…` | unchanged | An explicit driver choice is respected |
| *(unset)* | `sqlite:///…dogopaw.db` | Keeps development zero-config |

This is the single most common way a first Postgres deploy fails, and it fails
at startup with a message that does not mention the URL scheme at all.

### Connection pooling

Applied **only** when the URL is PostgreSQL — SQLite is a local file and needs
none of it:

| Setting | Value | Why |
|---|---|---|
| `pool_pre_ping` | `True` | Sends `SELECT 1` before handing out a pooled connection and silently replaces it if dead. Supabase's pooler closes idle connections and a free Render instance sleeps, so **without this the first request after idling fails** — which in a demo looks exactly like a broken site |
| `pool_recycle` | `280` s | Retires connections before Supabase's ~300 s idle cutoff can, so the pre-ping rarely has to do the work |
| `pool_size` / `max_overflow` | `5` / `2` | Modest, so several gunicorn workers together stay well inside the pooler's limit |
| `application_name` | `dogo-paw-api` | A hung query shows up as this app in Supabase's dashboard rather than an anonymous connection |

---

## 4. Schema

Seven core tables, plus five medical tables added by migration
`0002_medical_foundation` (see "Medical records" below). The same definitions
produce both backends; PostgreSQL types shown.

### `users`
| Column | Type | Notes |
|---|---|---|
| id | `SERIAL` PK | |
| name | `VARCHAR(120)` NOT NULL | |
| email | `VARCHAR(255)` NOT NULL | **UNIQUE**, indexed |
| password_hash | `VARCHAR(255)` NOT NULL | scrypt, 162 chars — fits with room to spare |
| is_admin | `BOOLEAN` NOT NULL | |
| created_at | `TIMESTAMP` NOT NULL | |

### `dogs`
| Column | Type | Notes |
|---|---|---|
| id | `SERIAL` PK | exposed as `dog_id` by the API |
| name | `VARCHAR(80)` NOT NULL | |
| age | `DOUBLE PRECISION` NOT NULL | |
| energy_level | `VARCHAR(20)` NOT NULL | low / medium / high |
| size | `VARCHAR(20)` NOT NULL | small / medium / large |
| temperament | `VARCHAR(40)` NOT NULL | |
| medical_needs, good_with_kids, good_with_other_pets | `BOOLEAN` NOT NULL | |
| photo_url | `VARCHAR(255)` NULL | added later; see §6 |
| bio | `TEXT` NULL | added later |
| created_at | `TIMESTAMP` NOT NULL | |

### `adopters`
One submitted questionnaire. `user_id` is **nullable** on purpose — a visitor
can use the matcher without an account, and a signed-in user can submit more
than once.

| Column | Type | Notes |
|---|---|---|
| id | `SERIAL` PK | |
| user_id | `INTEGER` NULL | **FK → users.id** |
| activity_level | `VARCHAR(20)` NOT NULL | |
| home_type | `VARCHAR(30)` NOT NULL | |
| experience_level | `VARCHAR(20)` NOT NULL | |
| has_kids, has_other_pets | `BOOLEAN` NOT NULL | |
| created_at | `TIMESTAMP` NOT NULL | |

### `match_requests`
Audit row written on every `/api/recommend`; the source of the dashboard's numbers.

| Column | Type | Notes |
|---|---|---|
| id | `SERIAL` PK | |
| user_id | `INTEGER` NULL | **FK → users.id** |
| adopter_id | `INTEGER` NOT NULL | **FK → adopters.id** |
| top_dog_id | `INTEGER` NULL | **FK → dogs.id** |
| top_score | `DOUBLE PRECISION` NULL | |
| results_count | `INTEGER` NOT NULL | |
| created_at | `TIMESTAMP` NOT NULL | indexed |

### `chatbot_logs`
| Column | Type | Notes |
|---|---|---|
| id | `SERIAL` PK | |
| user_id | `INTEGER` NULL | **FK → users.id** |
| question | `TEXT` NOT NULL | |
| predicted_intent | `VARCHAR(40)` NOT NULL | indexed |
| confidence | `DOUBLE PRECISION` NOT NULL | |
| low_confidence | `BOOLEAN` NOT NULL | |
| created_at | `TIMESTAMP` NOT NULL | indexed |

### `revoked_tokens`
The JWT denylist that makes logout a real revocation.

| Column | Type | Notes |
|---|---|---|
| id | `SERIAL` PK | |
| jti | `VARCHAR(36)` NOT NULL | **UNIQUE**, indexed |
| expires_at | `TIMESTAMP` NOT NULL | indexed; rows pruned past this |
| revoked_at | `TIMESTAMP` NOT NULL | |

### `volunteers`
| Column | Type | Notes |
|---|---|---|
| id | `SERIAL` PK | |
| name | `VARCHAR(120)` NOT NULL | |
| email | `VARCHAR(255)` NOT NULL | indexed |
| mobile | `VARCHAR(32)` NOT NULL | |
| address | `TEXT` NOT NULL | |
| state, city | `VARCHAR(80)` NOT NULL | |
| submitted_at | `TIMESTAMP` NOT NULL | indexed |

> This table holds real personal data — name, email, phone, home address. It is
> why the admin account is the most sensitive credential in the system.

### Medical records

Five tables, each owned by one dog. Every one has `dog_id INTEGER NOT NULL`
(**FK → dogs.id, ON DELETE CASCADE**, indexed), `recorded_by_id INTEGER NULL`
(**FK → users.id, ON DELETE SET NULL**: who entered it), and `created_at` /
`updated_at TIMESTAMP NOT NULL`. Calendar dates are `DATE`. Allowed values are
enforced twice: by the API, and by a `CHECK` constraint in the database.

| Table | Columns | Allowed values / constraints |
|---|---|---|
| `medical_records` | record_type `VARCHAR(20)`, title `VARCHAR(160)`, description `TEXT` NULL, veterinarian `VARCHAR(120)` NULL, visit_date `DATE` (indexed) | record_type: checkup, treatment, surgery, diagnostic, emergency, dental, other |
| `vaccinations` | vaccine_name `VARCHAR(120)`, administered_date `DATE` NULL, next_due_date `DATE` NULL (indexed), status `VARCHAR(20)`, veterinarian, notes | status: scheduled, completed, overdue |
| `medications` | medication_name `VARCHAR(120)`, dosage `VARCHAR(80)`, frequency `VARCHAR(80)`, start_date `DATE`, end_date `DATE` NULL (= ongoing), status (indexed), prescribed_by, notes | status: active, completed, discontinued |
| `health_observations` | observation_date `DATE` (indexed), weight_kg `DOUBLE` NULL, temperature_c `DOUBLE` NULL, symptoms `JSON` NULL (list of strings), notes | 0 < weight_kg ≤ 120; 30 ≤ temperature_c ≤ 45 |
| `follow_ups` | reason `VARCHAR(200)`, due_date `DATE` (indexed), completed_date `DATE` NULL, status (indexed), notes | status: pending, completed, missed, cancelled |

These are **not** part of `Dog.to_dict()`: `/api/dogs` and `/api/dogs/<id>`
return the same profile as before. Medical data is only served by the
authenticated `/api/dogs/<id>/medical` endpoints (`medical.py`).

Local demo data: `python medical_demo_data.py` adds a tagged fixture to five
dogs; `--clear` removes it. It refuses any non-local database and
`APP_ENV=production`.

### Health alerts and notifications

Added by migration `0003_health_alerts`.

`health_alerts` records a health-intelligence finding so it can be worked on.
Identity is **(dog_id, finding_code, entity_key)**, and the partial unique index
`uq_health_alerts_active_identity` (`WHERE status != 'resolved'`) allows only one
*active* alert per identity — that is what makes a repeated sync idempotent.
Resolved rows sit behind it as history and are never reused; a recurrence
becomes a new row pointing back through `reopened_from_id`.

| Column group | Columns |
|---|---|
| What was found (copied from the finding) | category, finding_code, entity_key, severity, title, reason, evidence `JSON`, recommendation |
| Snapshot | risk_score_at_detection (never updated) |
| Lifecycle | status (`open`/`acknowledged`/`resolved`), first_detected_at, last_detected_at, detection_count |
| Review | acknowledged_at/by_id, resolved_at/by_id, resolution_note, auto_resolved |
| Links | dog_id (**FK → dogs, CASCADE**), acknowledged_by_id / resolved_by_id (**FK → users, SET NULL**), reopened_from_id (**self FK, SET NULL**) |

`notifications` is an outbox: event_type, dog_id, alert_id, severity, payload
`JSON`, status (`pending`/`sent`/`failed`), channel, created_at, delivered_at.
**Nothing delivers from it** — every row this system writes stays `pending`.

Alerts are never deleted, and none of this appears in `/api/dogs` responses.

### No table for ML anomaly detection

The anomaly detector (`docs/REASONING.md`) adds **no tables**. Its results are
derived from `health_observations`, which are already stored, and recomputing
them costs microseconds against a cached model — so a table of every inference
would be a write path with no reader, going stale whenever the model changed.

Where an anomaly matters it becomes an ordinary `health_alerts` row under the
finding code `ml.health_anomaly`, which already persists the evidence, the
score and the model version, and already has a lifecycle.

### `0004_dog_id_sequence` — the dogs id sequence

`seed.py` inserts the 18 dogs with explicit ids, and PostgreSQL only advances a
`SERIAL` sequence when it supplies the value itself. So on every Postgres
database built this way `dogs_id_seq` sits at 1 while `MAX(id)` is 18, and the
first dog inserted **without** an explicit id fails with a duplicate key — as do
the next 17 attempts. Nothing reaches this today because no endpoint creates
dogs, which is exactly why it was worth fixing before one does.

Migration `0004` reads `MAX(id)` and moves the sequence past it. It inserts,
updates and deletes nothing and changes no schema, so it is safe against a live
database. On SQLite it is a deliberate no-op (there are no sequences), and its
downgrade does nothing, because rewinding would reintroduce the bug.

### Creation order

SQLAlchemy sorts by dependency, so foreign keys always resolve:

```
dogs → revoked_tokens → users → volunteers → adopters → chatbot_logs → match_requests
```

### Timestamps

Every timestamp is **naive UTC** — `datetime.now(timezone.utc)` with `tzinfo`
stripped — stored as `TIMESTAMP WITHOUT TIME ZONE`, and serialised by
`iso_utc()` with an explicit `Z`:

```json
"created_at": "2026-09-20T05:42:11Z"
```

Storing naive means what goes in is exactly what comes out, on both engines; the
explicit `Z` on the way out is what stops the browser reading a UTC time as
local. Consistency matters more than the choice itself — the important thing is
that one convention is used everywhere, which it is.

---

## 5. Environment variables

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | production | local SQLite file | Connection string; normalised as in §3 |
| `APP_ENV` | production | `development` | `production` makes the strict checks fire |
| `ADMIN_PASSWORD` | production | dev-only password | Seeded admin's password; min 12 chars |
| `SECRET_KEY` | production | generated `.secret_key` | JWT signing; min 32 chars |
| `DB_AUTO_MIGRATE` | no | `true` | `false` skips the startup migration and seed; for inspecting a database with `flask db` |

Full security context in [`SECURITY.md`](SECURITY.md). **Nothing above is ever
committed** — `.env` and `.env.*` are gitignored, with only `.env.example`
tracked.

---

## 6. Initialization

`seed()` runs automatically inside `create_app()`, so the database is ready on
first boot in both environments. It is **idempotent** — safe to run repeatedly:

1. `ensure_columns()` — adds `dogs.photo_url` / `dogs.bio` to a database that
   predates them. The old `create_all()` never touched an existing table, so
   without this an older database breaks on every dog query. Uses plain
   `ALTER TABLE … ADD COLUMN`, which works on both engines.
2. `migrate_to_head()` (`schema.py`) — brings the schema up to date with
   Alembic. See §8.
3. Dogs — inserted only if the table is empty; otherwise `photo_url` and `bio`
   are re-synced, since those are seed-owned content rather than user data.
4. Accounts — created only if that email does not already exist.

**No user data is ever overwritten.** Nothing here drops or rewrites a row a
visitor created.

### Concurrency: the advisory lock

Steps 1–4 are all *check-then-act*, which is safe with one process and a local
file and unsafe the moment a hosted app boots several gunicorn workers against
one database at the same time. Two workers can both see "no table" and both try
to create it; the loser fails the deploy with `relation already exists` or a
duplicate key.

`seed_lock()` wraps the whole thing in a **PostgreSQL advisory lock** — a named
lock the database holds for us, touching no table. The first worker in does the
work; the others wait, then find everything already done and no-op.

On SQLite it is a deliberate no-op: one process, one file, nothing to serialise.

```python
with seed_lock():      # pg_advisory_lock(4207311) on PostgreSQL, no-op on SQLite
    _seed(force)
```

Migrations run inside the same lock, so only one worker applies them. This is
why no separate "release command" or migration step is needed on Render: a
plain deploy is safe on its own.

### Seed accounts differ by environment

| | Development | Production |
|---|---|---|
| Admin | `admin@dogo-paw.org` / `admin123` | `admin@dogo-paw.org` / **`ADMIN_PASSWORD`** — startup fails if unset |
| Demo adopter | `demo@dogo-paw.org` / `demo123` | **not created** |
| 18 dogs | yes | yes |

The dogs are seed content and are identical in both. The accounts are not: a
deployed site never has an account whose password is written down in this
repository.

### Verifying it worked

`verify_db.py` runs 31 checks against whatever `DATABASE_URL` points at —
schema, unique constraints, foreign keys, relationships, timestamps, column
widths and every aggregate query the dashboard uses. It writes a few rows and
deletes them again, so it is safe against a live database; every row it creates
is prefixed `verify_db` so anything left by an interrupted run is obvious.

```bash
cd app/backend
python verify_db.py
```

Output names the backend it actually connected to, so it cannot be mistaken for
a local run.

---

## 7. Column widths are validated in the application

Because SQLite ignores `VARCHAR(n)` and PostgreSQL enforces it, a value that
saved fine locally could raise `DataError` — a **500** — in production. The API
therefore checks every field against its column's exact width:

| Field | Column | Validated at |
|---|---|---|
| user / volunteer name | `VARCHAR(120)` | 120 |
| email | `VARCHAR(255)` | 255 |
| password | — (hashed to 162) | 6–128 |
| volunteer mobile | `VARCHAR(32)` | 32 |
| volunteer state / city | `VARCHAR(80)` | 80 |
| volunteer address | `TEXT` | 500 |
| chatbot question | `TEXT` | 500 |

The mobile cap is the subtle one. The digit rule (10–15 digits after stripping
punctuation) does **not** bound the raw string, so
`"+91 (98765) 43210 extension 1234 bldg B"` — 43 characters, 16 digits — used to
pass length-wise and would have overflowed `VARCHAR(32)` on PostgreSQL. Both
rules now apply.

---

## 8. Migrations and upgrades

The schema is managed by **Flask-Migrate / Alembic**, adopted before the
medical-records work so new tables arrive as reviewed, versioned migrations.
Migration files live in `app/backend/migrations/versions/`.

### The baseline

`0001_baseline` is the seven tables exactly as `create_all()` built them up to
Phase 8. It is verified identical to the `create_all()` schema on both SQLite
and PostgreSQL (`test_migrations.py`). It applies differently depending on the
database:

| Database | What happens on startup |
|---|---|
| Empty (new local file, fresh Supabase project) | `upgrade` runs the baseline and creates all seven tables |
| Existing but unversioned (**production Supabase**, older local files) | Every baseline table and column is checked, then the baseline is **stamped**: `alembic_version` is created and set to `0001_baseline`. **No DDL runs and no rows are touched.** |
| Existing but missing a baseline table or column | Startup **refuses** with the list of what is missing, and stamps nothing |
| Already versioned | `upgrade` applies anything newer, or does nothing |

The baseline's `downgrade()` refuses to run, because undoing it would drop every
table.

### Adding a table or column

```bash
cd app/backend
# 1. edit models.py (new columns on existing tables should be nullable)
flask --app app db migrate -m "add vaccinations"   # autogenerate
# 2. READ the generated file in migrations/versions/ and fix anything wrong
flask --app app db upgrade                          # apply locally
python test_migrations.py                           # includes a drift check
```

Deploying applies it: on startup, `migrate_to_head()` runs `upgrade` inside the
advisory lock. Do not add columns through `LATER_COLUMNS` any more. That mechanism
only exists so pre-Phase-6 databases can still be stamped.

### Inspecting a database without changing it

Startup migrates by default. To run `flask db` commands against a database
without that happening first, set `DB_AUTO_MIGRATE=false`:

```bash
DB_AUTO_MIGRATE=false flask --app app db current        # which revision it is on
DB_AUTO_MIGRATE=false flask --app app db upgrade --sql  # print the SQL, run nothing
```

### Anything else

Renames, type changes and `NOT NULL` on populated tables all need a hand-edited
migration (autogenerate sees a rename as drop + add). Take a backup first; see §9.

### Resetting the database

```bash
python seed.py --reset      # drops every table and alembic_version, rebuilds, reseeds
```

**This destroys all data** — users, volunteers, match history. Fine locally,
essentially never correct in production.

---

## 9. Backups

### What Supabase gives you

The free tier takes **daily automatic backups with a 7-day retention**, restored
from the dashboard under Database → Backups. Paid tiers add point-in-time
recovery. For a college project the daily backup is adequate; know its limits —
up to 24 hours of data could be lost, and retention is a week.

### Take your own before anything risky

Before a manual schema change, a bulk delete or a `--reset`, take a dump you
control. Supabase's own backups are a safety net for *their* failures, not for
yours.

```bash
# Whole database
pg_dump "$DATABASE_URL" > backup-$(date +%F).sql

# Data only, no schema — useful for reseeding a rebuilt database
pg_dump --data-only "$DATABASE_URL" > data-$(date +%F).sql

# Restore
psql "$DATABASE_URL" < backup-2026-09-20.sql
```

`pg_dump` comes with the PostgreSQL client tools; it is not installed by this
project.

### What actually matters here

Not all seven tables are equally precious:

| Table | If lost | Why |
|---|---|---|
| `volunteers` | **Real loss** | Genuine sign-ups from real people, with their contact details. Irreplaceable |
| `users` | **Real loss** | Real accounts |
| `adopters`, `match_requests`, `chatbot_logs` | Recoverable | Activity history. Losing it empties the dashboard but breaks nothing; `demo_data.py` can repopulate a realistic week |
| `dogs` | No loss | Seed content, recreated on next boot |
| `revoked_tokens` | No loss | Losing it un-revokes already-expired tokens at worst |

So: **`volunteers` and `users` are the backup-worthy tables.** A weekly
`pg_dump` of those two, kept off Supabase, covers the realistic failure.

> A backup that has never been restored is a hope, not a backup. Restore one
> into a scratch Supabase project once, before you need to.

### Before the viva

Take a dump the morning of the demo. If something goes wrong mid-week you can
restore a known-good state rather than debugging live.

---

## 10. Testing against Supabase

The migration was verified as far as is possible without a server —
**41 PostgreSQL compatibility checks** (DDL generation for all 7 tables, URL
normalisation, driver resolution, pool settings, column-width validation) and
**31 `verify_db.py` checks** against SQLite.

**A real Supabase connection was not tested**, because no PostgreSQL server or
Docker was available in this environment and no Supabase credentials were
provided. That test is yours to run, and these are the exact commands.

### Step 1 — create the project

Supabase → **New project**. Note the database password; it appears once.

### Step 2 — get the pooler connection string

**Project Settings → Database → Connection string → Session Pooler** (port **5432**).

### Step 3 — run the verification

PowerShell:

```powershell
cd "D:\Dogo-Paw ITR\app\backend"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

$env:DATABASE_URL = "postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require"
$env:APP_ENV      = "production"
$env:SECRET_KEY   = python -c "import secrets; print(secrets.token_hex(32))"
$env:ADMIN_PASSWORD = "choose-a-strong-password"
$env:CORS_ORIGINS = "http://localhost:5173"

python verify_db.py
```

bash:

```bash
cd app/backend
source .venv/bin/activate
pip install -r requirements.txt

export DATABASE_URL="postgresql://postgres.PROJECT_REF:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres?sslmode=require"
export APP_ENV=production
export SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
export ADMIN_PASSWORD="choose-a-strong-password"
export CORS_ORIGINS="http://localhost:5173"

python verify_db.py
```

### What you should see

```
database backend : postgresql
server version   : PostgreSQL 15.x ...
...
  PASS  FK violation on match_requests.adopter_id [rejected]
  PASS  mobile over VARCHAR(32) [rejected by the column]
...
PASSED 31   FAILED 0
ALL DATABASE CHECKS PASSED on postgresql
```

Two lines read differently than on SQLite, and that is the point: those two
constraints are **enforced** on PostgreSQL and ignored by SQLite, so seeing
`[rejected]` is the confirmation that you are genuinely on Postgres.

### Step 4 — run the API suites against it

```bash
python test_recommender.py
RATE_LIMIT_ENABLED=false python verify_db.py
```

### Step 5 — check the tables exist

Supabase → **Table Editor**. You should see all seven, with `dogs` holding 18
rows and `users` holding exactly one (the admin — the demo adopter is
intentionally not created in production).

### If it fails

| Symptom | Cause | Fix |
|---|---|---|
| `Can't load plugin: sqlalchemy.dialects:postgres` | URL still `postgres://` and normalisation bypassed | Use the app; do not build the engine yourself |
| `ModuleNotFoundError: psycopg2` | URL names no driver and something skipped normalisation | `pip install -r requirements.txt`; confirm `psycopg[binary]` installed |
| `password authentication failed` | wrong password, or `[YOUR-PASSWORD]` left in the URL | Re-copy from the dashboard |
| `SSL connection has been closed unexpectedly` | direct connection instead of the pooler | Use the pooler host on port 5432 |
| `too many connections` | direct connection (`db.PROJECT_REF.supabase.co`) with several workers | Use the Session Pooler host on port 5432 |
| Migrations fail oddly, or prepared-statement errors | Transaction Pooler (port 6543) | Switch to the Session Pooler on port 5432 |
| Startup fails: `SECRET_KEY must be set` | `APP_ENV=production` without the rest | Set all four variables above |

---

## 11. Verification summary

| Check | Result |
|---|---|
| All 7 tables compile to valid PostgreSQL DDL | ✅ |
| Foreign keys (3 on `match_requests`) resolve, creation order is FK-aware | ✅ |
| Unique constraints on `users.email` and `revoked_tokens.jti` | ✅ |
| `SERIAL` / `BOOLEAN` / `TIMESTAMP WITHOUT TIME ZONE` mapping | ✅ |
| `postgres://` and `postgresql://` normalisation, driver untouched when explicit | ✅ |
| psycopg 3 dialect resolves | ✅ |
| `pool_pre_ping` / `pool_recycle` applied to Postgres only | ✅ |
| Every column-width overflow now returns 400, boundary values still accepted | ✅ |
| Seed advisory lock present; no-op on SQLite | ✅ |
| SQLite development path unchanged | ✅ 31/31 `verify_db.py` |
| Frontend has zero database coupling | ✅ |
| **Live Supabase connection** | ⚠️ **not run — see §10** |
