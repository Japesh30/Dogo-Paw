# Dogo-Paw — Security Model

How this application is secured for public deployment, and what it assumes.
Written to be read end to end in about ten minutes, and to be defensible in a
viva: every control below is something you can point at in the code and explain.

**Applies from:** Phase 3 (production security hardening), 2026-09-20.

---

## 1. The environment flag

One variable decides whether the app is allowed to be permissive:

```
APP_ENV=development   # default
APP_ENV=production
```

`app.py` derives `IS_PRODUCTION` from it once, and every control that must not
be lax in public keys off that single flag. This is deliberate: when asked
"is this safe to expose?", there is exactly one place to look.

**In production the app refuses to start** unless `SECRET_KEY`, `CORS_ORIGINS`
and `ADMIN_PASSWORD` are all set correctly. Failing loudly at boot is the point
— every one of these has a "convenient" default that is dangerous in public, and
a misconfigured deployment that *runs* is far worse than one that does not.

| Missing / wrong | Result |
|---|---|
| `SECRET_KEY` unset | startup fails, with the command to generate one |
| `SECRET_KEY` under 32 chars | startup fails |
| `CORS_ORIGINS` unset | startup fails |
| `CORS_ORIGINS=*` | startup fails |
| `ADMIN_PASSWORD` unset | startup fails |
| `ADMIN_PASSWORD` under 12 chars | startup fails |
| `python app.py` run at all | refuses, points at `gunicorn app:app` |

---

## 2. Authentication model

**Scheme:** JWT (HS256), 7-day expiry, sent as `Authorization: Bearer <token>`.

**Passwords** are hashed with `werkzeug.security.generate_password_hash`
(PBKDF2-HMAC-SHA256 with a per-password salt) and verified with
`check_password_hash`. Plaintext is never stored, never logged, and never
returned by any endpoint.

**Token contents** — `sub` (user id), `email`, `is_admin`, `jti`, `iat`, `exp`.
Nothing sensitive beyond the email is in the payload; a JWT is signed, not
encrypted, so anyone holding one can read its claims. The signature is what
makes the claims trustworthy, which is why `SECRET_KEY` handling matters so
much.

**Every request** passes through `load_user()` (a `before_request` hook), which
resolves the bearer token to a `User` or to `None`. A token is rejected if it is
absent, malformed, expired, signed with the wrong key, **or revoked**.

### Logout is real revocation

A session cookie is cleared server-side by definition. A JWT is not, because the
server keeps no session to clear — so by default "logging out" only asks the
browser to forget a token that still works.

Each token therefore carries a unique `jti`, and `POST /api/auth/logout` writes
that id to the `revoked_tokens` table. Any later request presenting the same
token is refused. Rows are pruned once past the token's own expiry, so the table
cannot grow without bound.

*Verified:* after logout, the same token returns **401** on the next request.

### Validation

| Field | Rule |
|---|---|
| name | required, non-blank, ≤ 120 chars, must be a string |
| email | required, ≤ 255 chars, must match the email pattern, lowercased on write |
| password | ≥ 6 chars, ≤ 128 chars, must be a string |

The 128-character password ceiling exists because hashing is intentionally
expensive: an unbounded password is free CPU for an attacker. Login also
short-circuits on an over-length email or password **before** hashing, so an
oversized body is never converted into work.

### Known trade-off: the token lives in `localStorage`

This is readable by any script running on the page, so a cross-site scripting
bug would expose it. It is a real trade-off, accepted deliberately:

- React escapes all interpolated content by default, and the codebase uses no
  `dangerouslySetInnerHTML` anywhere.
- The alternative — an `HttpOnly` cookie — would require CSRF protection and a
  same-site or proxied deployment, which does not fit a Vercel frontend calling
  a Render backend across origins.
- Blast radius is bounded by revocation and a 7-day expiry.

If this were handling payments or medical data the answer would be different.

---

## 3. Authorization model

Two levels, both enforced **on the server**:

| Decorator | Refuses with |
|---|---|
| `@login_required` | 401 if there is no valid caller |
| `@admin_required` | 401 if signed out, **403** if signed in but not an admin |

`is_admin` is read from the **database row**, not from the token's claim, at the
time of the request. A token claiming `is_admin: true` proves nothing unless it
also carries a valid signature, and the flag is re-read from the user record
regardless.

### The admin routes

| Route | Guard |
|---|---|
| `GET /api/admin/stats` | `@admin_required` |
| `GET /api/admin/adopter-segments` | `@admin_required` |

The React `ProtectedRoute requireAdmin` wrapper on `/admin` is **user
experience, not security** — it produces the redirect and the "Admin access
only" message. Anyone can edit client-side state; the server check is the one
that actually protects the data. Both are present, and the docs say plainly
which is which.

*Verified:* both admin routes return 401 anonymous, 403 for a signed-in
non-admin, and 401 for a forged `alg: none` token.

### What the admin dashboard exposes

Worth stating explicitly, because it sets the severity of everything above: the
dashboard shows every volunteer's **name, email, phone number and home
address**, every submitted adopter profile, and every question asked of the
chatbot. That is why the admin account is treated as the most sensitive thing
in the system.

---

## 4. CORS

```
CORS_ORIGINS=https://your-frontend-domain
```

- Comma-separated list of **exact origins**. Applied to `/api/*` only.
- **`*` is refused when `APP_ENV=production`** — with a wildcard, any site a
  visitor happens to be on can call this API from their browser.
- Development, with nothing set, falls back to `http://localhost:5173` and
  `http://127.0.0.1:5173`, so local work stays zero-config. Production has no
  fallback at all: unset means startup fails.
- `supports_credentials=False`. The API authenticates with a bearer token, never
  a cookie, so the browser is never asked to attach credentials cross-origin.

CORS is a **browser** control, not an access control. It stops other websites
using a visitor's browser as a proxy into this API; it does nothing about
`curl`. Authentication and rate limiting are what protect the endpoints
themselves.

---

## 5. Rate limiting

Implemented in `app/backend/ratelimit.py` — a fixed-window counter per
(rule, client IP), roughly forty lines.

| Endpoint | Limit | Why |
|---|---|---|
| `POST /api/auth/login` | **10 / 15 min** | stops online password guessing |
| `POST /api/auth/register` | **5 / hour** | stops bulk account creation |
| `POST /api/chatbot` | **20 / min** | each call writes a `ChatbotLog` row |
| `POST /api/recommend` | **10 / min** | each call writes a `MatchRequest` row |
| `POST /api/volunteer` | **5 / hour** | writes PII; a human submits once |

Reads (`/api/dogs`, `/api/health`) are **not** limited — they are cheap, cached
by the browser, and limiting them would only break legitimate browsing.

Over the limit returns **429** with a JSON body and a `Retry-After` header
giving the seconds to wait.

### Why not Flask-Limiter

Flask-Limiter is the standard answer, but with its default in-memory storage it
provides exactly what this module provides — a per-process counter — for the
cost of another dependency. The extra reliability only arrives with a shared
backend such as Redis, which this project does not have and does not need for a
single free-tier instance. Forty lines that can be read and explained in full
were judged the better trade for a project that has to be defended in a viva.

### Limitations — stated, not hidden

- **Per process.** Each gunicorn worker keeps its own counters, so with N
  workers the effective limit is up to N × the configured one. It still turns
  unlimited guessing into a slow trickle, which is the goal.
- **Resets on restart**, since counters live in memory.
- **Fixed window, not sliding** — a burst across a window boundary can briefly
  reach 2× the limit.

These are acceptable because the limits exist to stop casual automated abuse of
a public demo, not to meter a paid API.

### Client identity behind a proxy

The limiter keys on `request.remote_addr`. Behind Render's proxy that address is
the *proxy*, so in production `ProxyFix(x_for=1)` rewrites it from the first hop
of `X-Forwarded-For`. Without it every visitor would share one address and a
single abuser would lock out everybody. ProxyFix is enabled **only** in
production, because trusting `X-Forwarded-For` when you are not actually behind
a proxy would let a client spoof its own address and bypass the limiter.

---

## 6. Secrets management

| Secret | Where it comes from | Committed? |
|---|---|---|
| `SECRET_KEY` | environment; dev falls back to a generated `.secret_key` file | **No** — gitignored |
| `ADMIN_PASSWORD` | environment only | **No** |
| `DATABASE_URL` | environment (contains the DB password) | **No** |

**Nothing in `.env.example` is a real secret.** It contains placeholders, empty
values and the command to generate a key. It is the only `.env*` file that is
tracked, via an explicit `!.env.example` negation.

**The development key file.** With no `SECRET_KEY` set, development generates
`.secret_key` once and reuses it, so local startup needs no configuration
without every clone of this repo sharing a signing key. That path is **refused
in production**: a hosted filesystem is ephemeral, so the key would silently
change on each restart — invalidating every issued token and signing all users
out — and two instances would not accept each other's tokens.

### Git hygiene

`.gitignore` covers, and this was verified with `git check-ignore` against a
throwaway repository:

```
.env          .env.*        (but !.env.example)
*.db          .secret_key
.venv/  node_modules/  dist/  __pycache__/
```

`.env.*` matters as much as `.env`: Vite also reads `.env.production`,
`.env.development` and `.env.local`, and one of those committed out of habit is
a normal way for deployment configuration to become public. Before this phase
`.env.production` **would have been committed** — that gap is now closed.

No `.env` file, private key, certificate or credential exists in the working
tree. The only database file present (`dogopaw.db`) is generated on first run
and is ignored.

---

## 7. Input validation

Everything the React forms enforce is re-checked on the server. The client's
validation is for the user's benefit; the server's is the one that counts.

### Type safety

Every user-supplied string field is read through one helper:

```python
def text(data, key):
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""
```

JSON lets a caller send `{"name": {"$ne": null}}` or `{"name": 12}` as easily as
a string. Previously `.strip()` on those raised `AttributeError` and surfaced as
a **500**; now a wrong type becomes an ordinary **400**. A 500 is not just
untidy — it is an oracle, because it tells an attacker they reached code the
author did not expect to reach.

### Limits

| Input | Rule |
|---|---|
| **Request body (all endpoints)** | `MAX_CONTENT_LENGTH` = 64 KB → **413**, rejected before parsing |
| name | ≤ 120 chars, required |
| email | ≤ 255 chars, pattern-checked, lowercased |
| password | 6–128 chars |
| chatbot message | ≤ 500 chars, required |
| volunteer mobile | 10–15 digits after stripping non-digits |
| volunteer address | ≤ 500 chars |
| questionnaire fields | must be one of a fixed allow-list (`low`/`medium`/`high`, etc.) |
| `dog_id` | coerced to `int`, else 400 |

The `dog_id` coercion is not cosmetic: SQLite quietly returns no row for a
non-numeric id, but **PostgreSQL raises** — so after the Supabase migration the
same request would have become a 500 rather than a 404.

### SQL injection

All database access goes through SQLAlchemy's ORM with bound parameters. There
is no string-built SQL anywhere in the application. The one piece of raw SQL,
`ALTER TABLE dogs ADD COLUMN ...` in `seed.py`, interpolates only from a
hardcoded dict in the source — no user input reaches it.

---

## 8. Error responses

Every error leaves as the same JSON shape the client already handles:
`{"error": "..."}`.

| Status | Meaning |
|---|---|
| 400 | validation failed |
| 401 | not authenticated / token invalid or revoked |
| 403 | authenticated but not an admin |
| 404 | no such route or record |
| 405 | wrong method |
| 413 | body over 64 KB |
| 429 | rate limited |
| 500 | unexpected — **generic message only** |

A catch-all handler converts any unhandled exception into:

```json
{"error": "Something went wrong on our end. Please try again."}
```

The real exception goes to the **server log**, where the operator can see it.
The caller gets nothing. This keeps stack traces, SQLAlchemy error text, table
names, SQL fragments, file paths and library versions out of public responses —
Flask's default 500 page and a raw ORM exception would otherwise carry all of
them. The handler also rolls back the session, so a half-finished transaction is
never reused by the next request on that connection.

`PROPAGATE_EXCEPTIONS` and `DEBUG` are both pinned to `False` in config,
independently of any environment variable.

*Verified:* a deliberately raised exception containing a fake secret and a file
path returned the generic message, with neither value present in the body.

---

## 9. Debug configuration

The Werkzeug debugger offers an **interactive Python console** to anyone who can
trigger an exception. On a public host that is remote code execution. Three
independent things prevent it:

1. `app.config["DEBUG"] = False`, set unconditionally in `create_app()`.
2. `app.run(debug=True)` lives only under `if __name__ == "__main__"`, which a
   WSGI server never executes.
3. That block **refuses to run at all** when `APP_ENV=production`, exiting with
   a message pointing at `gunicorn app:app`.

Any one of these would do. All three are present because the cost of being wrong
here is total compromise.

---

## 10. Logging

The application logs startup progress (which models loaded, which accounts were
seeded by **email only**) and unhandled exceptions.

It does **not** log passwords, password hashes, JWTs, the signing key, the
database URL, or request bodies. Volunteer and adopter details are written to
the database because the feature requires it, never to the log.

The startup line for a generated development key prints the **filename**, never
the key.

---

## 11. Demo and default credentials

The single most serious finding of the Phase 1 audit was that the login page
printed **working admin credentials** (`admin@dogo-paw.org / admin123`) to every
visitor, and the same pair appeared in both READMEs. On a public deployment that
is not a weak password — it is a *published* one, granting anyone who opened the
page access to every volunteer's home address.

Fixed on three fronts:

1. **The UI.** The credential hint is wrapped in `import.meta.env.DEV`, which is
   `false` in any production build — so the bundler removes the block entirely
   rather than merely hiding it. The admin account is no longer named there at
   all; only the non-admin demo adopter is shown, in development.
2. **The seed.** In production the admin password comes from `ADMIN_PASSWORD`
   and startup fails without it (minimum 12 characters). The demo adopter is not
   created in production at all — it grants no privilege, but a public account
   with a published password is still a free foothold.
3. **The docs.** Both READMEs now state that those passwords are
   development-only and point here.

The dev passwords remain in `seed.py` **on purpose**: they are convenience
credentials for a local database containing nothing but seed data, and
`default_users()` refuses to use them in production. Removing them would have
broken local setup for no security gain — the protection is the environment
check, not secrecy.

---

## 12. Production security assumptions

What must be true for the controls above to hold. These are the honest
preconditions, not a guarantee.

1. **Environment variables are set correctly on the host** — `APP_ENV=production`
   above all. Without it the app runs in development mode and every relaxed
   default applies. This is the single most important line in the deployment
   configuration.
2. **`SECRET_KEY` is unique to the deployment, never committed, and stable
   across restarts.** Anyone holding it can mint a valid admin token.
3. **`ADMIN_PASSWORD` is strong and stored only in the host's secret manager.**
4. **TLS is terminated by the platform.** Vercel and Render both provide HTTPS;
   the application does not implement it. Over plain HTTP, bearer tokens are
   readable in transit and nothing here helps.
5. **The app runs behind exactly one trusted proxy** in production, which is
   what `ProxyFix(x_for=1)` assumes. Run it without a proxy and a client could
   spoof `X-Forwarded-For` to evade rate limiting.
6. **The database is reachable only over TLS** with credentials held in
   `DATABASE_URL` (`sslmode=require` for Supabase).
7. **The admin account is the crown jewel.** It reads every volunteer's PII.
   Treat its password accordingly.
8. **Rate limits are per process.** See §5 — they deter, they do not prevent.

### Accepted risks

Stated so they are decisions rather than oversights:

| Risk | Why accepted |
|---|---|
| JWT in `localStorage` | See §2. Bounded by revocation, short expiry, and no `dangerouslySetInnerHTML` in the codebase |
| Rate limits are per process and reset on restart | See §5. Proportionate to a single-instance demo |
| Chatbot questions stored indefinitely | They are the model's evaluation set, which is a documented feature of the project; questions are visitor-typed text, not solicited PII |
| Volunteer PII stored in plaintext | The feature requires it. Access is limited to the admin account; the database is not public |
| No account lockout or 2FA | Out of scope for a college project; rate limiting is the proportionate control |
| No automated dependency scanning in CI | There is no CI. `npm audit` reports 0 vulnerabilities as of this phase |

---

## 13. Verification

69 automated security checks were run against the hardened build, covering every
control in this document:

| Area | Checks | Result |
|---|---|---|
| `SECRET_KEY` enforcement | 6 | ✅ |
| CORS enforcement | 5 | ✅ |
| Debug configuration | 5 | ✅ |
| Demo / default credentials | 8 | ✅ |
| Input validation & type safety | 14 | ✅ |
| Admin authorization | 6 | ✅ |
| Error-response leakage | 10 | ✅ |
| Rate limiting | 9 | ✅ |
| Sensitive logging | 6 | ✅ |

All 77 functional workflow checks and the 16 recommender property checks still
pass, so nothing above was bought at the cost of a working feature.

---

## Reporting a problem

This is a student project, not a service with an on-call rota. If you find a
security issue in it, raise it with the repository owner directly rather than
opening a public issue.
