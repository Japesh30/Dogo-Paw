# Dogo-Paw — Privacy and Data Handling

What this application collects, why, where it is stored and who can see it.

**Applies from:** Phase 7, 2026-09-20.

> **Dogo-Paw is a student project.** It is not an operating charity, it is not a
> registered organisation, and this document is a factual description of the
> software's data handling — not a legal privacy policy. Nothing here claims
> compliance with any specific regulation. If this were ever to run as a real
> service, it would need a proper policy written for that context.

---

## 1. Summary

| | |
|---|---|
| **Personal data collected** | Volunteer sign-ups (name, email, phone, address) and user accounts (name, email) |
| **Sensitive categories** | None — no health, financial, biometric or government-ID data |
| **Payments** | None. The site takes no money and stores no card details |
| **Third-party analytics** | **None.** No Google Analytics, no tracking pixels, no advertising SDKs |
| **Third-party cookies** | **None** |
| **Data sold or shared** | **Never.** No data leaves the application's own database |
| **Where it is stored** | Supabase PostgreSQL (production) / a local SQLite file (development) |
| **Who can read it** | The project administrator, through the admin dashboard |

---

## 2. What is collected, and why

### 2.1 Volunteer sign-ups — the most sensitive data here

Collected by the form at `/volunteer`, stored in the `volunteers` table.

| Field | Why it is asked for | Required |
|---|---|---|
| Full name | To address the person | Yes |
| Email | To reply to the application | Yes |
| Mobile number | The stated follow-up method is a phone call | Yes |
| **Address** | To match a volunteer to nearby work | Yes |
| State, City | Regional grouping | Yes |

This is the only place the application asks for a **home address and phone
number**, which makes it the most sensitive data in the system and the reason
most of the controls in [`SECURITY.md`](SECURITY.md) exist.

**A privacy notice is shown on the form itself**, above the submit button —
before the person hands anything over, rather than behind a link or after the
fact. It states what is stored, that it is not sold or shared, that this is a
student project whose submissions are visible to the administrator, and how to
ask for removal.

> **Known limitation, stated plainly:** the address is a free-text field with no
> verification, and there is no automated deletion route — removal is a manual
> request. For a project of this size that is proportionate, but it is a
> limitation, not a feature.

### 2.2 User accounts

Collected at `/login`, stored in the `users` table.

| Field | Why | Stored as |
|---|---|---|
| Name | Shown in the UI and the admin activity feed | Plain text |
| Email | Login identity; unique | Plain text, lowercased |
| Password | Authentication | **scrypt hash, salted — never the plaintext** |

The plaintext password is never stored, never logged and never returned by any
endpoint. An account is optional: the adoption matcher and the chatbot both work
signed out.

### 2.3 Adoption questionnaire

Five answers — activity level, home type, experience level, whether there are
children, whether there are other pets — stored in `adopters`, plus an audit row
in `match_requests`.

Not linked to a person unless signed in (`user_id` is nullable). Signed out, the
row is anonymous and shows as "Guest".

Why it is stored rather than computed and discarded: it is what powers the admin
dashboard's activity figures and the k-means adopter segmentation, which are
themselves features of the project. It is household context, not identity.

### 2.4 Chatbot questions

Every question asked of the FAQ widget is stored in `chatbot_logs` with the
predicted intent and confidence.

**Why:** it doubles as the classifier's real-world evaluation set. Low-confidence
rows show exactly which intents need more training phrasings, which is part of
the project's ML write-up.

**The honest risk:** this is free text, so someone could type personal details
into it. Nothing solicits that, and the widget asks about adopting, fostering,
volunteering and donations — but a text box accepts anything. Messages are
capped at 500 characters and are visible to the administrator.

### 2.5 What is deliberately NOT collected

- No IP addresses stored. Rate limiting keys on the client address **in memory
  only** — never written to the database, and lost on restart.
- No cookies. Authentication uses a bearer token in `localStorage`, which is not
  sent automatically and is not a tracking cookie.
- No analytics, no tracking pixels, no advertising, no third-party scripts
  except Google Fonts (a stylesheet request, see §6).
- No location beyond the city/state a volunteer types.
- No uploads. There is nowhere to submit a file.

---

## 3. Where it is stored

| Environment | Database | Notes |
|---|---|---|
| Development | SQLite file, `app/backend/dogopaw.db` | Local only, gitignored, never committed |
| Production | Supabase PostgreSQL | Connection over TLS (`sslmode=require`) |

All access is through the Flask API. **The browser never talks to the database** —
there is no database client or credential in the frontend at all. Architecture
and schema are in [`DATABASE.md`](DATABASE.md).

---

## 4. Who can see it

| Role | Can see |
|---|---|
| Anonymous visitor | Only public content — dogs, pages, their own match results |
| Signed-in user | The above, plus their own account |
| **Administrator** | **Everything** — every volunteer's name, email, phone and address; every adopter profile; every chatbot question |

The admin dashboard is the reason the admin account is the most sensitive
credential in the system. It is guarded by `@admin_required` **on the server**,
and in production its password comes from an environment variable that is never
committed.

The single most serious finding of the original audit was that the login page
printed working admin credentials to every visitor — which meant the volunteer
table was effectively public. That is fixed; see [`SECURITY.md`](SECURITY.md) §11.

---

## 5. How it is protected

Summarised from [`SECURITY.md`](SECURITY.md):

- Passwords hashed with scrypt; plaintext never stored or logged.
- JWT authentication with real server-side revocation on logout.
- Admin routes enforced server-side, not just hidden in the UI.
- TLS everywhere — Vercel and Render terminate HTTPS; the database connection
  requires SSL.
- CORS pinned to the known frontend origin; `*` refused in production.
- Rate limiting on the volunteer form (5/hour) and the auth endpoints.
- Error responses never leak stack traces, SQL, table names or file paths.
- Logs contain no passwords, tokens, secrets or request bodies.

---

## 6. Third parties

| Service | What it receives | Why |
|---|---|---|
| **Vercel** | Serves the frontend. Standard web server logs (IP, user agent) under their own policy | Hosting |
| **Render** | Runs the API. Standard request logs — method, path, status, duration; **no headers, so no tokens** | Hosting |
| **Supabase** | Stores the database | Database |
| **Google Fonts** | The visitor's browser requests the Poppins stylesheet, which exposes their IP to Google | Typography |

**Google Fonts is the only third party the browser contacts**, and it is worth
naming because under some interpretations of EU rules that request alone is
treated as a data transfer. Self-hosting the font would remove it entirely —
a change worth making if this ever served EU users in earnest.

No analytics, advertising or tracking service is used.

---

## 7. Retention and deletion

**There is no automated retention policy.** Data is kept until removed by hand.
Stating that plainly is better than implying a policy that does not exist.

| Data | Retention |
|---|---|
| Volunteer sign-ups | Indefinite, until manually deleted |
| User accounts | Indefinite |
| Adopter profiles, match requests | Indefinite — they power the dashboard |
| Chatbot logs | Indefinite — they are the classifier's evaluation set |
| Revoked tokens | **Automatically pruned** once past their own expiry |

### Deleting someone's data

There is no self-service deletion. A request is handled manually:

```sql
-- Remove one volunteer's submission
DELETE FROM volunteers WHERE email = 'person@example.com';

-- Remove a user account and everything attached to it (children first —
-- PostgreSQL enforces the foreign keys)
DELETE FROM chatbot_logs  WHERE user_id = <id>;
DELETE FROM match_requests WHERE user_id = <id>;
DELETE FROM adopters       WHERE user_id = <id>;
DELETE FROM users          WHERE id = <id>;
```

Take a backup first — see [`DATABASE.md`](DATABASE.md) §9.

`clean_test_data.py` exists for removing rows created by automated test runs.
It matches only harness-generated names and never touches real submissions.

---

## 8. The demonstration data disclosure

Separate from privacy, but the same question of not misleading a visitor.

**The 18 dog profiles are synthetic.** They were generated for this project.
Their photographs are crops of ten real rescue photographs, reused across
profiles — they are not portraits of the individual animals.

Without saying so, the site reads as a live adoption listing. Someone could
believe a specific dog is waiting for them and get in touch about an animal that
does not exist — and the dog profile page has a "Call about &lt;name&gt;" button
that dials a real phone number.

It is therefore disclosed in four places:

1. **`/dogs`** — a notice above the gallery.
2. **`/dogs/:id`** — above the dog's name, before the call-to-action.
3. **`/adopt-match`** — above the ranked results.
4. **The footer** — on every route, including ones that show no dogs.

The wording is specific about what is and is not real:

> The 18 dogs shown here are a synthetic dataset created to demonstrate the
> adoption matcher — they are not real animals currently available for adoption,
> and the photographs are representative images reused across profiles rather
> than portraits of individual dogs. **The matching, scoring and explanations
> are genuine** — only the dogs are not.

That last clause matters: the recommender, the success model, the segmentation
and the classifier are all real working implementations. Overstating the
disclosure would undersell the actual work.

---

## 9. If this were to run for real

Not required for a student project; listed so the gap is understood rather than
overlooked.

1. A proper privacy policy written for the operating jurisdiction.
2. Self-service data export and deletion.
3. A defined retention period with automatic expiry.
4. Explicit consent capture, recorded with a timestamp.
5. Self-hosted fonts, removing the last third-party browser request.
6. A named data controller and a contact route for privacy requests.
7. A documented breach-notification procedure.
8. Encryption at rest beyond what Supabase provides by default.

---

## 10. Contact details on the site — flagged for review

These are in the source and shown publicly. **They were not invented or changed
by this work**, and they need a decision before the site is public:

| Detail | Where | Concern |
|---|---|---|
| `+91 70155 96198` | Footer, and the "Call about &lt;dog&gt;" button on every dog profile | Publishing a personal mobile number on a public site invites calls from strangers — and here, calls about dogs that do not exist |
| `hello@dogo-paw.org` | Footer | The domain is not owned by this project as far as can be told, so mail to it will not arrive |

See the Phase 7 report for the recommended options.
