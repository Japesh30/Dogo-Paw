# Dogo-Paw — Frontend Deployment (Vercel)

Everything needed to deploy the React + Vite frontend to Vercel. **Nothing has
been deployed yet** — this is the prepared configuration and the exact steps.

**Applies from:** Phase 6, 2026-09-20.

---

## 1. Vercel project settings

| Setting | Value |
|---|---|
| **Framework Preset** | Vite |
| **Root Directory** | `app/frontend` |
| **Build Command** | `npm run build` *(Vercel's default for Vite)* |
| **Output Directory** | `dist` *(Vercel's default for Vite)* |
| **Install Command** | `npm install` |
| **Node version** | 20.x or 22.x (either works; built and tested on 22.20.0) |

| Environment variable | Value |
|---|---|
| `VITE_API_URL` | `https://YOUR-BACKEND-DOMAIN` — your Render URL, **no trailing path** |

That is the entire configuration. Setting **Root Directory** to `app/frontend`
is the one step that is easy to miss: without it Vercel builds from the
repository root, finds no `package.json`, and fails.

---

## 2. `VITE_API_URL`

The frontend talks to the backend through exactly **one** `fetch`, in
[`src/lib/api.js`](../app/frontend/src/lib/api.js):

```js
const BASE = (import.meta.env.VITE_API_URL ?? '').replace(/\/+$/, '')
...
fetch(`${BASE}/api${path}`, { ... })
```

| Environment | `VITE_API_URL` | Request goes to |
|---|---|---|
| Local development | **unset** | `/api/dogs` → Vite dev server → proxied to Flask on `:5001` |
| Production | `https://dogo-paw-api.onrender.com` | `https://dogo-paw-api.onrender.com/api/dogs` |

**Leave it unset locally.** Unset is what keeps the Vite proxy in play; setting
it locally bypasses the proxy and usually produces CORS errors instead. See
[`app/frontend/.env.example`](../app/frontend/.env.example).

### It is baked in at build time, and it is public

Vite replaces `import.meta.env.VITE_API_URL` with a string literal *during the
build*. Two consequences worth understanding:

1. **Changing it requires a redeploy.** It is not read at runtime, so editing
   the variable in Vercel does nothing until the project is rebuilt. Vercel
   normally triggers a rebuild when you change an environment variable —
   confirm that it did.
2. **It ends up in the JavaScript bundle**, readable by anyone. That is correct
   here: it is a public API endpoint, configuration rather than a credential.
   **Never put a secret behind a `VITE_` prefix** — a password, key or token
   given that prefix is published to every visitor.

This is why the backend URL is *not* hardcoded in source: not because it is
secret, but because it differs per environment and must not be edited in code to
deploy.

### Trailing slashes are handled

`https://api.example.com/` would otherwise build `https://api.example.com//api/dogs`,
which some hosts 404 on. The trailing slash is stripped, because this value gets
pasted by hand into a dashboard. *Verified across five URL forms, including
multiple trailing slashes.*

---

## 3. SPA routing

React Router handles `/dogs`, `/dogs/3`, `/adopt-match`, `/admin` and the rest
**in the browser**. Those paths do not exist as files, so without a rewrite a
refresh or a shared deep link returns Vercel's 404 — the app would work when
navigated into and break when reloaded.

[`app/frontend/vercel.json`](../app/frontend/vercel.json):

```json
{ "rewrites": [{ "source": "/(.*)", "destination": "/index.html" }] }
```

### Why a catch-all does not break the images

This project has a genuine collision: **`/dogs` is both a route and a folder of
real files.** The gallery lives at `/dogs`, and each dog's photo is served from
`public/dogs/dog-01.jpg` — the API returns `photo_url: "/dogs/dog-01.jpg"`.

A catch-all rewrite looks like it would swallow those images. It does not,
because **Vercel checks the filesystem before applying rewrites**: redirects →
filesystem → rewrites. A request matching a real file gets that file; only
unmatched paths fall through to `index.html`.

An earlier draft of this config used a negative-lookahead pattern to exclude
`/assets/`. That was removed: it added complexity, and it covered only one of
the three asset folders, so it would have been inconsistent as well as
unnecessary.

**Verified against the real `dist/` output** with a server that mimics Vercel's
filesystem-first ordering:

| Request | Served as | |
|---|---|---|
| `/`, `/dogs`, `/dogs/3`, `/adopt-match`, `/admin`, `/login`, `/foster` | SPA rewrite → `index.html` | ✅ |
| `/dogs/dog-01.jpg` | **static file** (`image/jpeg`) | ✅ not shadowed |
| `/logo.png`, `/robots.txt`, `/media/video-1.mp4` | static files, correct MIME types | ✅ |
| `/assets/index-*.js` | static file | ✅ |

### Soft 404s

An unknown path such as `/nonexistent-page` returns **HTTP 200** with
`index.html`, and React Router renders the `NotFound` page. This is standard for
a single-page app and is what the catch-all rewrite means. The visitor sees the
right page; only the status code is technically wrong. Fixing it properly needs
server-side rendering, which is well beyond this project's scope.

---

## 4. Headers

Also in `vercel.json`, all defensible in a viva:

| Path | Header | Why |
|---|---|---|
| `/assets/*` | `Cache-Control: public, max-age=31536000, immutable` | Vite fingerprints these filenames with a content hash, so a changed file gets a new name. They can safely be cached forever |
| `/dogs/*`, `/media/*` | `Cache-Control: public, max-age=86400` | Not fingerprinted, so a day — long enough to matter for the 29 MB video, short enough to update |
| everything | `X-Content-Type-Options: nosniff` | Stops a browser guessing a type other than the one sent |
| everything | `Referrer-Policy: strict-origin-when-cross-origin` | Does not leak full paths to third parties |
| everything | `X-Frame-Options: SAMEORIGIN` | The site cannot be framed for clickjacking |

HTTPS is provided and enforced by Vercel; the app does nothing about it.

---

## 5. Assets and images

| Kind | Where | How it resolves |
|---|---|---|
| UI artwork (logo, banners, foster/volunteer photos) | `src/assets/images/` | Imported in `src/assets/images.js`, so Vite fingerprints and bundles them. Copied into `dist/assets/` |
| The 18 dog photos | `public/dogs/dog-NN.jpg` | Root-absolute `/dogs/dog-NN.jpg`, from the API's `photo_url`. Copied to `dist/dogs/` |
| Hero video (29 MB) | `public/media/video-1.mp4` | Kept in `public/` deliberately so Vite never tries to inline 29 MB into the bundle |
| Favicon | `public/logo.png` | `/logo.png` |
| `robots.txt` | `public/robots.txt` | `/robots.txt` |

**The images are served by Vercel, not by the backend.** `photo_url` is a
site-relative path, so the photos keep working regardless of where the API
lives, and a sleeping backend does not blank the gallery.

Every dog also has a drawn SVG fallback (`DogAvatar`) if `photo_url` is missing,
so a dog added by hand still renders.

---

## 6. Page titles and SEO

### Per-route titles

A single-page app never reloads, so before this phase **every route shared one
`<title>`** — every tab, bookmark and history entry read "Dogo-Paw — Rescue,
Foster, Adopt", including a specific dog's page.

`Layout.jsx` now sets the title from the path, in the effect that already
existed for scroll restoration:

| Route | Title |
|---|---|
| `/` | Rescue, Foster, Adopt · Dogo-Paw |
| `/about` | About us · Dogo-Paw |
| `/dogs` | Our dogs · Dogo-Paw |
| `/dogs/:id` | Dog profile · Dogo-Paw |
| `/volunteer` | Volunteer with us · Dogo-Paw |
| `/foster` | Foster a dog · Dogo-Paw |
| `/login` | Sign in · Dogo-Paw |
| `/adopt-match` | Find your match · Dogo-Paw |
| `/admin` | Admin dashboard · Dogo-Paw |
| anything else | Page not found · Dogo-Paw |

It lives in one place on purpose. Two components both writing `document.title`
would race on effect ordering, and which one won would depend on when a fetch
happened to resolve.

> **Known limitation, deliberate:** a dog's page says "Dog profile" rather than
> "Bruno", because the name is not known until the profile page's own fetch
> resolves. Having `DogProfile` set it once loaded is a few lines, at the cost
> of that ordering subtlety.

### Metadata

`index.html` carries a description, `theme-color`, and Open Graph / Twitter card
tags so a shared link renders a preview instead of a bare URL.

`og:image` is **site-relative** (`/logo.png`), which the major crawlers resolve
against the page being shared. That keeps the deployment domain out of the
source — nothing to edit when the URL changes.

**These tags are static and site-level.** A crawler reads the raw HTML before
any JavaScript runs, so per-route social cards would need server-side rendering.
One accurate site-level card is the honest thing to ship for a client-rendered
app; claiming otherwise would just be wrong metadata.

`public/robots.txt` allows crawling and asks crawlers to skip `/admin` and
`/login`. That is tidiness, not security — a `Disallow` is a request, and both
routes are already guarded server-side.

---

## 7. Mobile responsiveness

Audited, no changes needed. The UI was already built mobile-first:

- `<meta name="viewport" content="width=device-width, initial-scale=1.0">` present.
- **197 responsive class prefixes** (`sm:` / `md:` / `lg:` / `xl:`) across the
  components — layouts genuinely reflow rather than shrink.
- The page container is `mx-auto w-full max-w-6xl px-5 sm:px-8` — a 20 px gutter
  on phones, widening on larger screens.
- **No fixed pixel widths that could force horizontal scroll.** The only two
  hard numbers are both correct:
  - `max-w-[220px]` on the dashboard sparkline — a *maximum*, not a fixed width.
  - `min-w-[720px]` on the admin match-requests table, wrapped in
    `overflow-x-auto` — the right pattern for a wide data table on a phone: the
    table scrolls, the page does not.
- Checkboxes are sized 20 px rather than the browser's 13 px default, with a
  comment explaining why (smallest tap target on the page).

No UI or design changes were made in this phase.

---

## 8. Deploying

1. Push the repository to GitHub. *(Not done yet — Phase 7.)*
2. Vercel → **Add New → Project** → import the repository.
3. Set **Root Directory** to `app/frontend`. Framework preset should
   auto-detect as **Vite**; leave build command and output directory at their
   defaults.
4. Add the environment variable:
   ```
   VITE_API_URL = https://YOUR-BACKEND-DOMAIN
   ```
   Apply it to **Production**, **Preview** and **Development**.
5. **Deploy.**
6. Copy the resulting URL (e.g. `https://dogo-paw.vercel.app`) and set it as
   `CORS_ORIGINS` on the Render backend. **The two must know about each other** —
   see §10.

### `vercel.json` location

It sits in `app/frontend/`, alongside `package.json`, because that is the
project root Vercel is given. A `vercel.json` at the repository root would be
ignored with this setting.

---

## 9. Verifying the deployment

```bash
# 1. The site loads
curl -sI https://YOUR-APP.vercel.app | head -1          # 200

# 2. Deep links work — this is what the rewrite is for
curl -sI https://YOUR-APP.vercel.app/dogs/3 | head -1   # 200, not 404
curl -sI https://YOUR-APP.vercel.app/adopt-match | head -1

# 3. Images are NOT swallowed by the rewrite
curl -sI https://YOUR-APP.vercel.app/dogs/dog-01.jpg | grep -i content-type
# image/jpeg   <- must NOT be text/html

# 4. The backend URL was baked into the bundle
curl -s https://YOUR-APP.vercel.app/assets/index-*.js | grep -o "https://[a-z0-9-]*\.onrender\.com" | head -1

# 5. Security headers
curl -sI https://YOUR-APP.vercel.app | grep -iE "x-content-type|referrer-policy|x-frame"
```

In the browser, confirm end to end:

- `/dogs` lists 18 dogs **with photos** — proves both the API call and the
  static images.
- `/adopt-match` returns ranked matches — proves `POST /api/recommend` and the
  ML models.
- The chat widget answers — proves the classifier.
- `/admin` redirects to login when signed out; signing in as a non-admin gives
  "Admin access only".
- **Refresh the page on `/dogs/3`.** If it 404s, the rewrite is not applied.
- The tab title changes as you navigate.
- Open it on a phone, or DevTools at 375 px width.

---

## 10. The two-sided configuration

The frontend and backend each need to know the other's URL, which is circular on
a first deploy:

| Side | Variable | Value |
|---|---|---|
| Vercel | `VITE_API_URL` | the Render URL |
| Render | `CORS_ORIGINS` | the Vercel URL |

Deploy the backend first, deploy the frontend with its URL, then set
`CORS_ORIGINS` on Render to the Vercel domain. Both need a rebuild/restart after
the value changes — and `VITE_API_URL` in particular is **baked in at build
time**, so it needs a genuine rebuild, not just a restart.

**If the site loads but every API call fails**, this is almost always why. Check
the browser console: a CORS error means `CORS_ORIGINS` does not match the Vercel
origin exactly — including `https://`, and with **no trailing slash**.

---

## 11. What was verified, and what was not

### Verified

| Check | Result |
|---|---|
| `npm run lint` | ✅ clean, 0 warnings |
| `npm run build` | ✅ 689 kB / 204 kB gzip |
| Exactly one `fetch` in the whole frontend, in `lib/api.js` | ✅ |
| No hardcoded backend or localhost URLs in source | ✅ (only three placeholder social links) |
| `VITE_API_URL` baked into the bundle when set | ✅ |
| URL joins correctly for 5 forms, incl. multiple trailing slashes | ✅ 9/9 |
| Production build strips the dev-only offline message | ✅ |
| **Demo credentials absent from the production bundle** | ✅ |
| No `console.log` / `debugger` / `alert` anywhere in source or bundle | ✅ |
| SPA routing against the real `dist/`, Vercel-ordering simulated | ✅ 8 routes |
| `/dogs/dog-01.jpg` served as a static image, not shadowed | ✅ |
| All static assets present in `dist/` with correct MIME types | ✅ |
| API error handling after the `api.js` change | ✅ 6/6 |
| Viewport meta, 197 responsive prefixes, no overflow-forcing widths | ✅ |

### Not verified

| Not tested | Why |
|---|---|
| **Vercel itself** | Nothing deployed — that is Phase 7. Routing was verified against the real build with Vercel's documented filesystem-first ordering, but only the real platform confirms it |
| **The live frontend↔backend pair** | The backend is not deployed either. §9 covers it once both are up |
| **Real device testing** | Responsiveness audited from the code, not on hardware. Check one real phone before the viva |
| **Social card rendering** | Tags are correct and site-relative; how a specific platform renders them can only be checked once there is a public URL |
