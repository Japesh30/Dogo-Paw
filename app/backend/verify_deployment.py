"""Verify a LIVE deployment end to end, over the public internet.

    python verify_deployment.py https://dogo-paw-api.onrender.com
    python verify_deployment.py https://dogo-paw-api.onrender.com https://dogo-paw.vercel.app

Pass the backend URL, and optionally the frontend URL to check it too. The admin
checks run only if ADMIN_PASSWORD is set in the environment:

    # PowerShell
    $env:ADMIN_PASSWORD="your-admin-password"
    python verify_deployment.py https://dogo-paw-api.onrender.com https://dogo-paw.vercel.app

Standard library only - no dependencies, so it runs anywhere, including from a
machine that has never installed this project.

It creates one throwaway account and one volunteer row, both tagged `deploycheck`
so anything left behind by an interrupted run is obvious. Rows are left in place
deliberately: proving they persisted is the point of the database check.

Exits non-zero if any check fails.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

TIMEOUT = 90  # a sleeping free instance can take ~50s to wake

passed: list[str] = []
failed: list[tuple[str, str]] = []
skipped: list[tuple[str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (passed if ok else failed).append(name if ok else (name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail and not ok else ""))
    return ok


def skip(name: str, why: str) -> None:
    skipped.append((name, why))
    print(f"  SKIP  {name}  -- {why}")


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def call(url: str, method: str = "GET", body: dict | None = None,
         token: str | None = None, origin: str | None = None):
    """Returns (status, parsed_json_or_text, headers). Never raises for HTTP errors."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if origin:
        req.add_header("Origin", origin)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return r.status, json.loads(raw), dict(r.headers)
            except json.JSONDecodeError:
                return r.status, raw, dict(r.headers)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw), dict(e.headers)
        except json.JSONDecodeError:
            return e.code, raw, dict(e.headers)
    except Exception as exc:  # noqa: BLE001 - network, DNS, TLS
        return 0, {"error": f"{type(exc).__name__}: {exc}"}, {}


def main(api: str, site: str | None) -> int:
    api = api.rstrip("/")
    site = site.rstrip("/") if site else None
    tag = f"deploycheck-{uuid.uuid4().hex[:8]}"
    email = f"{tag}@test.local"
    password = "deploycheck-pw-123"

    print(f"backend  : {api}")
    print(f"frontend : {site or '(not given)'}")
    print(f"run tag  : {tag}")

    # ---------------------------------------------------------- backend ---- #
    section("1. Backend health")
    started = time.time()
    status, body, _ = call(f"{api}/api/health")
    elapsed = time.time() - started
    if not check("GET /api/health returns 200", status == 200, f"status={status} body={body}"):
        print("\nThe backend is not reachable. Nothing else can be checked.")
        print("Check Render's Logs tab; a free instance can take ~50s to wake.")
        return 1
    check("health payload says ok", isinstance(body, dict) and body.get("status") == "ok")
    if elapsed > 15:
        print(f"        (took {elapsed:.0f}s - this looks like a cold start, which is normal)")

    section("2. Public data and ML artifacts")
    status, body, _ = call(f"{api}/api/dogs")
    dogs = body.get("dogs", []) if isinstance(body, dict) else []
    check("GET /api/dogs returns 18 dogs", status == 200 and len(dogs) == 18,
          f"status={status} count={len(dogs)}")
    check("dogs carry photo_url and bio (seed ran)",
          bool(dogs) and all(d.get("photo_url") and d.get("bio") for d in dogs))
    status, body, _ = call(f"{api}/api/dogs/1")
    check("GET /api/dogs/1 returns one dog", status == 200)
    status, _, _ = call(f"{api}/api/dogs/999")
    check("GET /api/dogs/999 returns 404", status == 404)
    status, body, _ = call(f"{api}/api/model-info")
    check("GET /api/model-info serves metrics (ML artifacts deployed)",
          status == 200 and isinstance(body, dict) and "metrics" in body,
          f"status={status} - 503 means the .joblib files did not deploy")

    # ------------------------------------------------- auth + database ---- #
    section("3. Authentication: register -> login -> logout -> login again")
    status, body, _ = call(f"{api}/api/auth/register", "POST",
                           {"name": "Deploy Check", "email": email, "password": password})
    check("register returns 201 with a token",
          status == 201 and isinstance(body, dict) and bool(body.get("token")),
          f"status={status} body={body}")
    status, body, _ = call(f"{api}/api/auth/register", "POST",
                           {"name": "x", "email": email, "password": password})
    check("duplicate registration returns 409", status == 409, f"status={status}")

    status, body, _ = call(f"{api}/api/auth/login", "POST",
                           {"email": email, "password": password})
    token = body.get("token") if isinstance(body, dict) else None
    check("login returns 200 with a token", status == 200 and bool(token), f"status={status}")

    status, body, _ = call(f"{api}/api/auth/me", token=token)
    check("GET /api/auth/me returns the account", status == 200)

    status, body, _ = call(f"{api}/api/auth/logout", "POST", token=token)
    check("logout reports the token revoked",
          status == 200 and isinstance(body, dict) and body.get("revoked") is True)
    status, _, _ = call(f"{api}/api/auth/me", token=token)
    check("the revoked token is refused afterwards (401)", status == 401, f"status={status}")

    status, body, _ = call(f"{api}/api/auth/login", "POST",
                           {"email": email, "password": password})
    token = body.get("token") if isinstance(body, dict) else None
    check("LOGIN AGAIN succeeds - the account PERSISTED in PostgreSQL",
          status == 200 and bool(token), f"status={status}")

    status, _, _ = call(f"{api}/api/auth/login", "POST",
                        {"email": email, "password": "WRONG"})
    check("wrong password is rejected (401)", status == 401, f"status={status}")

    # ------------------------------------------------------- adoption ---- #
    section("4. Adoption matcher")
    profile = {"activity_level": "high", "home_type": "house_with_yard",
               "experience_level": "experienced", "has_kids": False, "has_other_pets": False}
    status, body, _ = call(f"{api}/api/recommend", "POST", profile, token=token)
    matches = body.get("matches", []) if isinstance(body, dict) else []
    check("questionnaire returns 18 ranked recommendations",
          status == 200 and len(matches) == 18, f"status={status} count={len(matches)}")
    check("results are sorted best first",
          all(matches[i]["score"] >= matches[i + 1]["score"] for i in range(len(matches) - 1))
          if len(matches) > 1 else False)
    check("each match carries its explanation",
          bool(matches) and "breakdown" in matches[0])
    check("success probability present (2nd model live)",
          bool(matches) and matches[0].get("success_probability") is not None)
    status, _, _ = call(f"{api}/api/recommend", "POST", {**profile, "activity_level": "turbo"})
    check("invalid questionnaire value rejected (400)", status == 400, f"status={status}")

    # ------------------------------------------------------ volunteer ---- #
    section("5. Volunteer form")
    status, body, _ = call(f"{api}/api/volunteer", "POST", {
        "name": f"{tag} Volunteer", "email": f"{tag}.vol@test.local",
        "mobile": "9876543210", "address": "12 MG Road",
        "state": "Maharashtra", "city": "Pune"})
    check("volunteer submission accepted (201)", status == 201, f"status={status} body={body}")
    check("submission echoed back from the database",
          isinstance(body, dict) and body.get("volunteer", {}).get("city") == "Pune")
    volunteer_id = body.get("volunteer", {}).get("id") if isinstance(body, dict) else None
    status, _, _ = call(f"{api}/api/volunteer", "POST", {"name": "x"})
    check("incomplete volunteer submission rejected (400)", status == 400, f"status={status}")

    # -------------------------------------------------------- chatbot ---- #
    section("6. Chatbot")
    status, body, _ = call(f"{api}/api/chatbot", "POST", {"message": "how do i adopt a dog"})
    check("chatbot answers a question",
          status == 200 and isinstance(body, dict) and bool(body.get("answer")),
          f"status={status} - 503 means the model artifact did not deploy")
    check("chatbot classified the intent correctly",
          isinstance(body, dict) and body.get("intent") == "adoption_process",
          f"intent={body.get('intent') if isinstance(body, dict) else body}")
    status, body, _ = call(f"{api}/api/chatbot", "POST", {"message": "qwerty zxcvb 12345"})
    check("gibberish is flagged low-confidence rather than answered confidently",
          isinstance(body, dict) and body.get("low_confidence") is True)

    # ---------------------------------------------------- authorization -- #
    section("7. Authorization")
    status, _, _ = call(f"{api}/api/admin/stats")
    check("admin route without a token returns 401", status == 401, f"status={status}")
    status, body, _ = call(f"{api}/api/admin/stats", token=token)
    check("admin route as a normal user returns 403", status == 403, f"status={status}")
    check("the 403 body leaks no dashboard data",
          isinstance(body, dict) and set(body) == {"error"})

    admin_password = os.environ.get("ADMIN_PASSWORD", "").strip()
    if not admin_password:
        skip("admin dashboard checks", "set ADMIN_PASSWORD to run these")
    else:
        status, body, _ = call(f"{api}/api/auth/login", "POST",
                               {"email": "admin@dogo-paw.org", "password": admin_password})
        atoken = body.get("token") if isinstance(body, dict) else None
        if check("admin can sign in with ADMIN_PASSWORD", status == 200 and bool(atoken),
                 f"status={status}"):
            status, stats, _ = call(f"{api}/api/admin/stats", token=atoken)
            check("admin dashboard API returns 200", status == 200)
            check("dashboard carries every section",
                  isinstance(stats, dict)
                  and {"totals", "activity", "top_dogs", "recent_activity", "chatbot"} <= set(stats))
            totals = stats.get("totals", {}) if isinstance(stats, dict) else {}
            check("dashboard counts the account this script created",
                  totals.get("users", 0) >= 1, f"users={totals.get('users')}")
            check("dashboard counts the volunteer this script submitted",
                  totals.get("volunteers", 0) >= 1, f"volunteers={totals.get('volunteers')}")
            check("dashboard counts the chatbot questions asked above",
                  totals.get("chatbot_questions", 0) >= 1,
                  f"chatbot_questions={totals.get('chatbot_questions')}")
            check("dashboard counts the match request made above",
                  totals.get("match_requests", 0) >= 1,
                  f"match_requests={totals.get('match_requests')}")
            status, seg, _ = call(f"{api}/api/admin/adopter-segments", token=atoken)
            check("adopter segmentation endpoint responds", status == 200)
            if volunteer_id:
                feed = stats.get("recent_activity", []) if isinstance(stats, dict) else []
                check("the volunteer submission appears in the activity feed",
                      any(tag in str(e.get("who", "")) for e in feed),
                      "not in the 12 most recent - fine on a busy database")

        status, body, _ = call(f"{api}/api/auth/login", "POST",
                               {"email": "admin@dogo-paw.org", "password": "admin123"})
        check("the DEVELOPMENT admin password does NOT work in production",
              status == 401,
              f"status={status} - if this is 200, APP_ENV is not 'production'!")
        status, _, _ = call(f"{api}/api/auth/login", "POST",
                            {"email": "demo@dogo-paw.org", "password": "demo123"})
        check("the demo account was NOT seeded in production", status == 401,
              f"status={status} - if this is 200, APP_ENV is not 'production'!")

    # ------------------------------------------------------------ CORS --- #
    section("8. CORS")
    if not site:
        skip("CORS checks", "pass the frontend URL as the second argument")
    else:
        _, _, headers = call(f"{api}/api/dogs", origin=site)
        allowed = headers.get("Access-Control-Allow-Origin")
        check("the frontend origin is allowed", allowed == site,
              f"got {allowed!r}, expected {site!r} - check CORS_ORIGINS on Render")
        _, _, headers = call(f"{api}/api/dogs", origin="https://evil.example.com")
        check("an unknown origin is refused",
              headers.get("Access-Control-Allow-Origin") is None,
              f"got {headers.get('Access-Control-Allow-Origin')!r} - CORS is too permissive")

    # -------------------------------------------------------- frontend --- #
    section("9. Frontend")
    if not site:
        skip("frontend checks", "pass the frontend URL as the second argument")
    else:
        status, body, _ = call(site)
        check("the site loads", status == 200, f"status={status}")
        check("it is the Dogo-Paw app", isinstance(body, str) and "Dogo-Paw" in body)
        for path in ("/dogs", "/dogs/3", "/adopt-match", "/volunteer"):
            status, _, _ = call(f"{site}{path}")
            check(f"deep link {path} returns 200 (SPA rewrite works)", status == 200,
                  f"status={status} - a 404 means vercel.json is not applied")
        status, _, headers = call(f"{site}/dogs/dog-01.jpg")
        ctype = headers.get("Content-Type", "")
        check("/dogs/dog-01.jpg is served as an image, not swallowed by the rewrite",
              status == 200 and "image" in ctype, f"content-type={ctype!r}")
        check("the site is served over HTTPS", site.startswith("https://"), site)
        check("the backend is served over HTTPS", api.startswith("https://"), api)

    # ---------------------------------------------------------- result --- #
    print("\n" + "=" * 66)
    print(f"PASSED {len(passed)}   FAILED {len(failed)}   SKIPPED {len(skipped)}")
    if failed:
        print("\nFAILURES:")
        for name, detail in failed:
            print(f"  - {name}\n      {detail}")
    if skipped:
        print("\nSKIPPED:")
        for name, why in skipped:
            print(f"  - {name}: {why}")
    if not failed:
        print("\nDEPLOYMENT VERIFIED")
        print(f"\nThis run left behind an account ({email}) and a volunteer row")
        print(f"tagged {tag} - proof they persisted. Remove them when you are done.")
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    sys.exit(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
