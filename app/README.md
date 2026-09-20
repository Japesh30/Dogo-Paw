# Dogo-Paw

A rebuild of the original static Dogo-Paw site as a React + Flask application,
with an adoption-matching recommender as the core feature.

```
app/
├─ frontend/          Vite + React 19 + Tailwind 4 + React Router 7
│  ├─ src/pages/      one component per route
│  ├─ src/components/ Navbar, Footer, Carousel, MatchCard, charts…
│  ├─ src/assets/     images carried over from the old assest/image folder
│  ├─ public/dogs/    one generated gallery photo per dog
│  └─ scripts/        image optimiser + dog-photo builder
└─ backend/           Flask 3 + SQLAlchemy + SQLite
   ├─ app.py          API routes
   ├─ models.py       User, Dog, Adopter, MatchRequest
   ├─ recommender.py  the matching engine
   ├─ seed.py         18-dog dataset (+ bios, photos) + default accounts
   └─ demo_data.py    optional: a week of activity for the dashboard
```

## Running it

Two terminals.

**Backend** (http://127.0.0.1:5001):

```powershell
cd app\backend
.\.venv\Scripts\Activate.ps1      # or: python -m venv .venv; pip install -r requirements.txt
python app.py
```

The database is created and seeded automatically on first run.

If you already had a database from an earlier phase, `seed.ensure_columns()`
adds the newer `dogs.photo_url` and `dogs.bio` columns in place and backfills
them. `create_all()` only creates missing *tables*, and SQLite has no
`ADD COLUMN IF NOT EXISTS`, so without that step an older database would break
on every dog query — and dropping the file would take your users, volunteers
and match history with it.

**Frontend** (http://localhost:5173):

```powershell
cd app\frontend
npm install
npm run dev
```

Vite proxies `/api/*` to the Flask server, so there is nothing to configure.

### Demo accounts

Created by `seed.py`:

| Email | Password | Role |
|---|---|---|
| admin@dogo-paw.org | admin123 | admin — can open `/admin` |
| demo@dogo-paw.org | demo123 | regular adopter |

Development only. With `APP_ENV=production` the admin password comes from
`ADMIN_PASSWORD` (startup fails without it) and the demo adopter is not seeded.
The login page's credential hint is likewise compiled out of production builds.
See [`../docs/SECURITY.md`](../docs/SECURITY.md).

### Populating the dashboard

A fresh database has no activity, so the dashboard charts show a single day.
To fill a realistic week (real recommendations, backdated timestamps):

```powershell
python demo_data.py           # ~40 requests over 7 days
python demo_data.py --clear   # wipe activity again
```

## The matching engine

`recommender.py`. Both sides are projected into the same normalised 3-D space
`[energy, space, experience]` — the dog vector is what the dog *requires*, the
adopter vector is what the adopter *offers*:

| Axis | Dog side | Adopter side |
|---|---|---|
| energy | `energy_level` low/medium/high → 0 / 0.5 / 1 | `activity_level`, same scale |
| space | `size` small/medium/large → 0 / 0.5 / 1 | `home_type` apartment / house-no-yard / house-with-yard |
| experience | `temperament` (calm 0 → protective 0.9), +0.2 if `medical_needs` | `experience_level` none / some / experienced |

```
score = (1 - euclidean_distance / sqrt(3)) * 100
```

`sqrt(3)` is the diagonal of the unit cube — the furthest two profiles can be
apart — so the score lands on 0–100. Two safety rules then apply as
multipliers, because they are constraints rather than preferences:

* adopter has children **and** dog is not kid-friendly → **× 0.4**
* adopter has other pets **and** dog is not pet-friendly → **× 0.5**

Every response carries the breakdown — raw distance, per-axis gaps, which
penalties fired and why — which is what the match cards display.

Run the checks with:

```powershell
python test_recommender.py
```

## API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/auth/register` | — | create an account, returns a JWT |
| POST | `/api/auth/login` | — | sign in, returns a JWT |
| GET | `/api/auth/me` | bearer | current user |
| POST | `/api/auth/logout` | bearer | revokes the caller's token server-side |
| GET | `/api/dogs` | — | all 18 dogs, full profile including `photo_url` and `bio` |
| GET | `/api/dogs/<id>` | — | one dog, or 404 |
| POST | `/api/volunteer` | — | volunteer sign-up; validated server-side, writes to `volunteers` |
| POST | `/api/recommend` | optional | ranked matches + breakdown + success probability; logs a `MatchRequest` |
| POST | `/api/predict-success` | — | logistic-regression success probability for one adopter-dog pair |
| GET | `/api/model-info` | — | success model metrics + coefficients |
| POST | `/api/chatbot` | optional | intent + answer; logs a `ChatbotLog` |
| GET | `/api/admin/stats` | admin | totals, 7-day activity, top dogs, activity feed, chatbot activity |
| GET | `/api/admin/adopter-segments` | admin | k-means personas with auto-derived labels |
| GET | `/api/health` | — | liveness |

`/api/recommend` works signed out (the request is logged against "Guest"), so a
visitor can try the matcher before creating an account.

### Auth

Passwords are hashed with `werkzeug.security.generate_password_hash` and checked
with `check_password_hash`; the plaintext is never stored. Sign-in returns a JWT
(7-day expiry) which the React `AuthProvider` keeps in `localStorage` and
re-hydrates through `/api/auth/me` on refresh.

Logging out is a real revocation, not just a forgotten token. A session cookie
is cleared server-side by definition, but a JWT is not — the server holds no
session to clear — so each token carries a unique `jti` and
`/api/auth/logout` writes that id to a `revoked_tokens` table. Any later request
presenting the same token is rejected, and rows are pruned once past the
token's own expiry. `/admin` is guarded twice: `ProtectedRoute` on the client
for the redirect and the access-denied message, and `@admin_required` on the
server, which is the one that actually matters.

## The other three models

All live in `backend/ml/`, all share `ml/features.py` so "adopter energy level"
means the same number everywhere, and all are trained offline and loaded once at
startup — no request ever retrains anything.

```bash
cd app/backend
python -m ml.success_model     # train + evaluate the success predictor
python -m ml.chatbot           # train + evaluate the intent classifier
python -m ml.segmentation      # cluster the live adopter table and print
python -m ml.chatbot "how do i foster"   # try one question
```

### Adoption success predictor — logistic regression (supervised)

Trained on 300 synthetic adopter-dog pairs whose labels are sampled from a
compatibility-driven probability, so the model has to *find* the relationships
rather than being handed them.

| Metric | Value |
|---|---|
| Test accuracy (25% holdout) | **65.3%** |
| 5-fold CV accuracy | **69.0%** (± 5.2) |
| ROC AUC | **0.756** |
| Bayes ceiling | **70.1%** |

That last row is the one that makes the others readable. Labels are sampled
`Bernoulli(p)`, so even a model that knew `p` exactly would only be right
`max(p, 1-p)` of the time — 70.1% on average. At 69.0% CV the model reaches
**98.5% of what is achievable**; the remaining gap is noise, not a modelling
failure. Quoting 69% without the ceiling would make a near-optimal model look
mediocre.

The strongest learned coefficients are `kid_conflict` (−0.97) and
`pet_conflict` (−0.75), then `space_gap` and `energy_gap` — the model recovered
the safety constraints on its own.

*Note on features:* temperament is encoded ordinally via
`TEMPERAMENT_EXPERIENCE_SCALE`. Adding a 10-column one-hot for it as well
**cost** 1.7 points of CV accuracy (67.3% vs 69.0%), because it duplicates
signal already present and adds variance. `INCLUDE_TEMPERAMENT_ONEHOT` in
`ml/features.py` flips it back on to reproduce that.

### Adopter segmentation — k-means (unsupervised)

Clusters every submitted adopter profile on `[energy, space, experience,
has_kids, has_other_pets]`. `k` is chosen by silhouette score between 3 and 4
rather than asserted.

Cluster names are **derived, not hardcoded**: `label_centroid` compares each
centroid against the mean of all centroids and names whichever traits deviate
most, widening to more traits if two clusters would otherwise collide. Feed it
different adopters and the names follow the data — a hardcoded
cluster-number-to-name map would silently go wrong the moment k-means renumbers
its clusters.

### FAQ chatbot — TF-IDF + Multinomial Naive Bayes (NLP)

7 intents, 156 training phrasings, word n-grams unioned with `char_wb` n-grams
so it survives real typos ("voluntear" → `volunteer_info` at 0.998 confidence).

| Metric | Value |
|---|---|
| 5-fold CV accuracy | **73.0%** |
| Validation accuracy | 100% *(see below)* |
| **Final test accuracy** | **75.0%** on 20 unseen phrasings |
| Useful response rate | **90.0%** |

Three sets, deliberately. The first holdout showed which intents had thin
vocabulary and the training examples were widened in response — which makes it a
*validation* set, and its 100% is flattering rather than informative. The final
test set was written afterwards, evaluated once, and the training data was not
touched again. **75% is the honest number.**

"Useful response rate" is what a visitor experiences: a correct answer, or an
honest "I'm not sure, here's a human" when confidence falls below 0.40. Only a
confidently wrong answer counts as a failure. The 0.40 threshold was read off
the confidence distribution — every correct answer scored 0.49+, so raising the
bar from 0.30 to 0.40 lost nothing and converted two confident errors into
fallbacks.

## The dog gallery

`/dogs` fetches all 18 once and filters **client-side**. Chips within a group
are OR'd, groups are AND'd — the standard faceted behaviour — so "Small or
Large, with Low energy, good with kids" is expressible, and the combination that
yields nothing shows an empty state rather than a blank grid. Eighteen rows is
nothing to send, and filtering in the browser means no request per keystroke.

`/dogs/:id` shows the bio and every attribute, and — if the visitor has been
through the questionnaire in this tab — their compatibility score, predicted
success and the per-axis reasoning for *this* dog.

That last part is the bit worth explaining. The obvious implementation is to
re-POST `/api/recommend` from the profile page, and it is wrong: that endpoint
writes a `MatchRequest` audit row on every call, so browsing dog pages would
quietly inflate the dashboard with recommendations nobody asked for. Instead
`/adopt-match` stores its own response in `sessionStorage`
(`lib/matchSession.js`) and the profile page reads the score out of it. No
request, no phantom analytics, and the number cannot disagree with what the
visitor already saw. `sessionStorage` rather than `localStorage` because a
matching profile describes a household *right now* — it should not still be
claiming to tomorrow.

### The photos

The dataset is synthetic, so none of the 18 dogs has a photograph. The options
were a stock-photo API (dies without a network — i.e. during a demo), a drawn
placeholder for all 18 (honest but the grid looks unfinished), or the ten real
rescue photographs already sitting in `src/assets/images`. The third one won.

`npm run build:dog-photos` crops one 900×675 image per dog into `public/dogs/`
using sharp's `attention` strategy, which finds the busiest region of the frame
— reliably the dog rather than the pavement. Sources are grouped by build, and
matched to temperament where the pool allows (the eight-year-old gets the
resting senior; the ten-month-old gets the puppy). Ten photos across eighteen
dogs means reuse, so a repeated source is **mirrored or zoomed** so it does not
read as copy-paste in the grid — mirroring and zooming rather than a fixed
gravity, because a fixed gravity can crop the dog out of the frame and these
cannot. 18 files, 1.08 MB total.

Every image is captioned **"Representative photo"**, and `DogPhoto` falls back
to the drawn `DogAvatar` for any dog with no `photo_url`.

The database stores the site-relative path (`/dogs/dog-13.jpg`), so the column
is genuinely a URL and swapping in real photographs later means replacing files
and updating a string — no code change.

## The volunteer form

Migrated out of the standalone `form/dog-volunteer` Vite app and its
Node/Express/MongoDB backend. It now lives at
`src/components/VolunteerForm.jsx`, rendered in the `#signup` section of
`/volunteer`, and writes to the `volunteers` table in the same SQLite database
as everything else. **There is only one backend.**

Same six fields and the same rules as the original — name, valid email, mobile
of at least 10 digits, address, state, city — with two deliberate changes:

* The `localStorage` draft was dropped. It does not survive every
  deployment/preview environment, and a half-typed address is not worth
  persisting. Form state is plain React state.
* Every rule is re-checked in Flask before the insert, because client-side
  validation is a convenience, not a control — a direct `POST` bypasses it
  entirely.

The old `form/dog-volunteer/` Vite app and `volunteer-backend/` Node service
have been deleted now that the migration is verified — there is no second
backend to start by mistake.

| Then | Now |
|---|---|
| `POST /api/volunteer` on Express, port 5000 | `POST /api/volunteer` in `backend/app.py` |
| MongoDB `volunteers` collection via Mongoose | `volunteers` table in `backend/dogopaw.db` |
| `fetch("http://localhost:5000/...")` | shared API client → Flask |
| Validation on the client only | Same rules re-checked before insert |
| Standalone CSS | The app's Tailwind design tokens |

## Notes on the migrated assets

* Source images were 51 MB straight off a camera; `npm run optimize:images`
  (already applied) took them to 3.9 MB with no visible loss.
* `video-1.mp4` lives in `public/media/` so Vite never tries to inline 28 MB.
* `dog2.png`, `dog3.png`, `dog5.png` and `banner1.png` turned out to be finished
  campaign graphics with their own text and logos — not transparent cutouts —
  so they are displayed as artwork rather than used as backdrops. Dogs in the
  synthetic dataset have no photos, so match cards use a drawn placeholder.
