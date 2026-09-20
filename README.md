# Dogo-Paw

A dog rescue and adoption site for **Dogo-Paw**, a non-profit, shelterless,
all-breed rescue run by volunteers. Rebuilt from a static HTML/Bootstrap site
into a React + Flask application, with a content-based **adoption-matching
recommender** as its core feature: an adopter answers five questions and every
dog in foster care is scored against their profile, with the reasoning for each
score shown alongside it.

Final-year college project.

## What it does

| Feature | What it is |
|---|---|
| **Adoption matching** | Answer five questions; every dog is scored against your profile and each score is explained axis by axis |
| **Adoption success prediction** | A second, independent model estimates how likely each pairing is to last |
| **Adopter segmentation** | The admin dashboard clusters every submitted profile into named adopter personas |
| **FAQ assistant** | A floating chat widget that classifies the question and answers from site content — or admits it does not know |
| **Dog gallery** | Browse all 18 dogs, filter by size / energy / household, search by name, open a full profile with bio and photo |
| **Volunteer sign-up** | Six roles plus a form that validates on both sides and writes to the database |
| **Accounts** | Register / sign in with JWTs, real server-side logout revocation |
| **Admin dashboard** | Totals, a 7-day activity chart, top dogs, adopter segments, FAQ-assistant activity and a combined feed — behind a double-guarded admin route |

Four of those are machine learning, and they are **four different paradigms**
rather than four uses of one: a distance-based recommender, supervised
classification, unsupervised clustering, and NLP text classification. Metrics
are in [The four ML components](#the-four-ml-components) below.

## Tech stack

| Layer | Used |
|---|---|
| Frontend | React 19, Vite, React Router 7, Tailwind CSS 4, Recharts |
| Backend | Python 3, Flask 3, Flask-SQLAlchemy, PyJWT, Werkzeug |
| Database | SQLite (single file, pre-seeded) |
| ML / scoring | NumPy, scikit-learn, joblib |

## Running it locally

You need **Node 18+** and **Python 3.10+**. Two terminals.

### 1. Backend → http://127.0.0.1:5001

```bash
cd app/backend
python -m venv .venv
.venv\Scripts\activate         # Windows
# source .venv/bin/activate    # macOS / Linux
pip install -r requirements.txt
python app.py
```

### 2. Frontend → http://localhost:5173

```bash
cd app/frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api/*` to Flask, so there is
nothing to configure.

> **No `.env` file is needed.** The backend runs on built-in defaults. On first
> start it generates a random signing key into `app/backend/.secret_key`
> (gitignored) rather than using a shared hardcoded one, so startup stays
> zero-config without every clone sharing the same key. Copy
> `app/backend/.env.example` to `.env` if you want to set `SECRET_KEY`,
> `DATABASE_URL`, `CORS_ORIGINS` or `PORT` yourself.

## The database is pre-seeded

`app/backend/dogopaw.db` is created and populated automatically on first run —
**18 dogs** and two accounts. You do not need to import anything.

| Email | Password | Role |
|---|---|---|
| `admin@dogo-paw.org` | `admin123` | Admin — can open `/admin` |
| `demo@dogo-paw.org` | `demo123` | Regular adopter |

> **These are local development passwords only.** They work against a database
> that contains nothing but seed data. When `APP_ENV=production` the backend
> refuses to start without `ADMIN_PASSWORD` set in the environment, and the
> demo adopter is not created at all — so a deployed site never has an account
> whose password is written down in this repository. See
> [`docs/SECURITY.md`](docs/SECURITY.md).

To also fill the dashboard with a week of activity (real recommendations, only
the timestamps are backdated):

```bash
cd app/backend
python demo_data.py           # ~40 match requests + 10 volunteer sign-ups
python demo_data.py --clear   # remove it again
```

## Pages

| Route | What it does |
|---|---|
| `/` | Hero with looping background video, entry points to the three paths |
| `/about` | Who we are, the rescue-to-adoption process, what we fund |
| `/dogs` | Browse every dog, filter by size / energy / household, search by name |
| `/dogs/:id` | One dog's full profile, bio, and your match score if you have one |
| `/volunteer` | The six volunteer roles + a sign-up form that writes to the database |
| `/foster` | Why fostering matters, photo carousel, FAQs, campaign posters |
| `/login` | Sign in / sign up, tabbed, with client and server validation |
| `/adopt-match` | **The AI feature** — questionnaire, ranked dogs, per-match explanation |
| `/admin` | Protected dashboard: totals, 7-day activity chart, combined activity feed |

### Browsing and matching are joined up

The gallery and the matcher are the same 18 dogs seen two ways. Once you have
answered the questionnaire, every card in `/dogs` carries its score and each
profile page shows the full reasoning — **without re-running the matcher**. The
results are held in `sessionStorage`, because `/api/recommend` writes an audit
row on every call, and browsing dog pages must not invent recommendations
nobody asked for.

### About the photos

The 18 dogs are a **synthetic dataset** — they have no photographs of their own.
Rather than depend on an internet photo service (which fails exactly when you
need it, mid-demo), each dog is given a crop of one of the **ten real rescue
photographs already in the repo**, generated by `npm run build:dog-photos`,
grouped by build so a small dog never gets a shepherd's photo. Ten photos across
eighteen dogs means some are reused, so repeats are mirrored or re-cropped, and
every image is captioned **"Representative photo"** rather than implying it is
that specific animal.

## How the matching works

Both sides become a point in the same normalised space
`[energy, space, experience]`. The dog vector is what the dog *requires*; the
adopter vector is what the adopter *offers*.

```
score = (1 - euclidean_distance / sqrt(3)) * 100
```

`sqrt(3)` is the diagonal of the unit cube — the furthest two profiles can be
apart — which puts the score on 0–100. Two safety rules then apply as
multipliers, because they are constraints rather than preferences:

* adopter has children **and** dog is not kid-friendly → **× 0.4**
* adopter has other pets **and** dog is not pet-friendly → **× 0.5**

Nothing is hidden from the user: all 18 dogs are returned ranked, and each card
explains its own score, including when a penalty was applied and why.

Run the checks on the algorithm with:

```bash
cd app/backend
python test_recommender.py
```

## The four ML components

| Feature | Paradigm | Model | Headline metric |
|---|---|---|---|
| Adoption matching | distance-based | euclidean in a 3-D profile space | 16/16 property checks pass |
| Adoption success | supervised | LogisticRegression | **65.3% test**, 69.0% CV, AUC 0.756 (ceiling 70.1%) |
| Adopter segments | unsupervised | KMeans | k chosen by silhouette; labels derived from centroids |
| FAQ assistant | NLP | TF-IDF + MultinomialNB | **75.0%** on a once-only test set; 90% useful responses |

Full write-up, including why the success model's 69% is near-optimal rather
than mediocre, is in [`app/README.md`](app/README.md).

Retrain or re-evaluate any of them:

```bash
cd app/backend
python -m ml.success_model     # train + evaluate the success predictor
python -m ml.chatbot           # train + evaluate the intent classifier
python -m ml.segmentation      # cluster the live adopter table and print
```

## The admin dashboard

`/admin`, signed in as the admin account. It shows:

* **summary cards** — dogs, registered users, adopter profiles, volunteers,
  match requests, chatbot questions, average top score
* **7-day activity chart** — match requests and volunteer sign-ups on one axis
* **top dogs** — which dogs come first most often
* **adopter segments** — the k-means personas, with `k`, the silhouette score
  and the profile count shown so the clustering is inspectable rather than
  asserted
* **FAQ assistant activity** — questions asked, by intent, plus the most recent
  ones, with low-confidence rows flagged
* **combined activity feed** and a **match request table**

The route is guarded twice: `ProtectedRoute` on the client for the redirect and
the access-denied message, and `@admin_required` on the server, which is the one
that actually matters. A signed-out visitor is asked to sign in; a signed-in
non-admin gets a clear "Admin access only" message. Neither ever sees dashboard
content.

## Project layout

```
app/
├─ frontend/          React app (see app/README.md for detail)
│  └─ public/dogs/    generated gallery photo per dog
└─ backend/
   ├─ app.py          Flask API
   ├─ recommender.py  the matching engine
   ├─ ml/             the other three models + shared feature encoding
   ├─ seed.py         18 dogs, bios, default accounts
   └─ dogopaw.db      created and seeded on first run (not in the repo)
dogo paw frontend/    the original static site, kept for reference
```

`node_modules/`, `.venv/`, `dist/`, `dogopaw.db` and `.secret_key` are all
gitignored — they are regenerated by the install and first-run steps above, and
none of them should be submitted.

Deeper technical notes — full API table, auth/revocation design, the gallery and
photo approach, the asset migration — are in [`app/README.md`](app/README.md).
