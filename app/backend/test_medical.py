"""
Checks for the medical-record foundation: schema, migration, authorization,
create/read/update, validation, and that the existing dog API is unchanged.

    python test_medical.py
    python test_medical.py --postgres postgresql://postgres@127.0.0.1:5432/scratch

Each engine runs in its own child process against a throwaway database. The
--postgres URL must be a local, EMPTY, disposable database: its public schema is
dropped and recreated. Anything not on this machine is refused.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
MEDICAL_TABLES = {"medical_records", "vaccinations", "medications", "health_observations", "follow_ups"}
BASELINE_TABLES = {"users", "dogs", "adopters", "chatbot_logs", "revoked_tokens", "volunteers", "match_requests"}
HEAD = "0004_dog_id_sequence"
DOG_KEYS = {
    "dog_id", "name", "age", "energy_level", "size", "temperament", "medical_needs",
    "good_with_kids", "good_with_other_pets", "photo_url", "bio",
}

FAILURES: list[str] = []


def check(label: str, condition: bool, detail: object = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f"  ({detail})" if detail != "" and not condition else ""))
    if not condition:
        FAILURES.append(label)


def section(title: str) -> None:
    print(f"\n{title}")


# --------------------------------------------------------------------------- #
# Everything below runs in the child, with DATABASE_URL already pointing at a
# throwaway database.
# --------------------------------------------------------------------------- #
def run_checks() -> None:
    import app as app_module
    from flask_migrate import downgrade, upgrade
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import IntegrityError

    import medical
    import medical_demo_data
    from models import Dog, FollowUp, HealthObservation, User, Vaccination, db

    app = app_module.app
    client = app.test_client()
    anchor = date(2026, 9, 1)
    today = date.today()

    def login(email, password):
        response = client.post("/api/auth/login", json={"email": email, "password": password})
        return {"Authorization": f"Bearer {response.json['token']}"}

    admin = login("admin@dogo-paw.org", "admin123")
    user = login("demo@dogo-paw.org", "demo123")

    with app.app_context():
        is_pg = db.engine.dialect.name == "postgresql"
        print(f"engine: {db.engine.dialect.name}")

        # ------------------------------------------------------------ schema
        section("1. Schema and migration")
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        check("all five medical tables exist", MEDICAL_TABLES <= tables, MEDICAL_TABLES - tables)
        check("baseline tables still exist", BASELINE_TABLES <= tables)
        version = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        check(f"database is at {HEAD}", version == HEAD, version)
        for table in MEDICAL_TABLES:
            fks = {(tuple(fk["constrained_columns"]), fk["referred_table"]) for fk in insp.get_foreign_keys(table)}
            check(f"{table}.dog_id references dogs", (("dog_id",), "dogs") in fks)
            check(f"{table}.dog_id is indexed",
                  any(ix["column_names"] == ["dog_id"] for ix in insp.get_indexes(table)))
            dog_col = next(c for c in insp.get_columns(table) if c["name"] == "dog_id")
            check(f"{table}.dog_id is NOT NULL", dog_col["nullable"] is False)
        dog_columns = {c["name"] for c in insp.get_columns("dogs")}
        check("dogs table gained no columns", dog_columns == {
            "id", "name", "age", "energy_level", "size", "temperament", "medical_needs",
            "good_with_kids", "good_with_other_pets", "photo_url", "bio", "created_at"})

        # ----------------------------------------------------- DB constraints
        section("2. Database-level constraints")

        def rejected(row) -> bool:
            db.session.add(row)
            try:
                db.session.commit()
                return False
            except IntegrityError:
                db.session.rollback()
                return True

        check("CHECK rejects an invalid vaccination status",
              rejected(Vaccination(dog_id=1, vaccine_name="X", status="bogus")))
        check("CHECK rejects a zero weight",
              rejected(HealthObservation(dog_id=1, observation_date=today, weight_kg=0)))
        check("CHECK rejects a temperature of 50 °C",
              rejected(HealthObservation(dog_id=1, observation_date=today, temperature_c=50)))
        check("NOT NULL rejects a follow-up without a dog",
              rejected(FollowUp(reason="x", due_date=today, status="pending")))
        if is_pg:
            check("FK rejects a record for a non-existent dog (PostgreSQL)",
                  rejected(FollowUp(dog_id=99999, reason="x", due_date=today, status="pending")))
        else:
            print("  [skip] FK enforcement: SQLite does not enforce foreign keys by default; "
                  "the API checks the dog exists instead (section 6)")

        # ------------------------------------------------------ relationships
        section("3. Fixture and relationships")
        added = medical_demo_data.load(anchor)
        check("demo fixture loads", added == 31, added)
        check("fixture load is idempotent", medical_demo_data.load(anchor) == 0)
        rocky = db.session.get(Dog, 4)
        check("dog.medications", [m.medication_name for m in rocky.medications] == ["Phenobarbital"])
        check("dog.health_observations newest first",
              [o.observation_date for o in rocky.health_observations]
              == sorted((o.observation_date for o in rocky.health_observations), reverse=True))
        check("dog.follow_ups soonest first",
              [f.due_date for f in rocky.follow_ups] == sorted(f.due_date for f in rocky.follow_ups))
        check("dog.medical_records", len(rocky.medical_records) == 1)
        check("dog.vaccinations", len(db.session.get(Dog, 1).vaccinations) == 2)
        check("Dog.to_dict() carries no medical data", set(rocky.to_dict()) == DOG_KEYS)

        # Every fixture row must also satisfy the API's own rules, so later
        # phases are never tested against data the API could not produce.
        bad = []
        for kind, resource in medical.RESOURCES.items():
            for row in resource["model"].query.all():
                body = {k: v for k, v in row.to_dict().items() if k in resource["fields"]}
                try:
                    medical.parse(resource, body)
                except medical.Invalid as exc:
                    bad.append(f"{kind} {row.id}: {exc}")
        check("every fixture row passes API validation", not bad, bad[:3])

        # Cascade: a dog removed takes its medical rows with it.
        if is_pg:
            # Regression: seed.py inserts dogs 1-18 with explicit ids, which
            # leaves dogs_id_seq at 1 on PostgreSQL, so the first dog created
            # without an id collided on the primary key. Migration
            # 0004_dog_id_sequence advances the sequence past the seeded rows.
            auto = Dog(name="Auto id", age=2, energy_level="low", size="small",
                       temperament="calm")
            db.session.add(auto)
            try:
                db.session.commit()
                check("a dog can be created without an explicit id (dogs_id_seq)",
                      auto.id > 18, auto.id)
                db.session.delete(auto)
                db.session.commit()
            except IntegrityError as exc:
                db.session.rollback()
                check("a dog can be created without an explicit id (dogs_id_seq)",
                      False, str(exc).splitlines()[0][:80])

        # Explicit id below, so the cascade check does not depend on the
        # sequence being correct.
        temp = Dog(id=9001, name="Temp", age=1, energy_level="low", size="small", temperament="calm")
        db.session.add(temp)
        db.session.commit()
        db.session.add_all([
            FollowUp(dog_id=temp.id, reason="x", due_date=today, status="pending"),
            HealthObservation(dog_id=temp.id, observation_date=today, weight_kg=5),
        ])
        db.session.commit()
        temp_id = temp.id
        db.session.delete(temp)
        db.session.commit()
        left = (FollowUp.query.filter_by(dog_id=temp_id).count()
                + HealthObservation.query.filter_by(dog_id=temp_id).count())
        check("deleting a dog cascades to its medical rows", left == 0, left)
        check("other dogs' medical rows untouched", FollowUp.query.filter_by(dog_id=4).count() == 2)

        if is_pg:
            # recorded_by_id is SET NULL: removing an account keeps the record.
            staff = User(name="Staff", email="staff@example.com", password_hash="x", is_admin=True)
            db.session.add(staff)
            db.session.commit()
            row = FollowUp(dog_id=1, reason="x", due_date=today, status="pending", recorded_by_id=staff.id)
            db.session.add(row)
            db.session.commit()
            row_id = row.id
            db.session.execute(text("DELETE FROM users WHERE id = :id"), {"id": staff.id})
            db.session.commit()
            db.session.expire_all()
            kept = db.session.get(FollowUp, row_id)
            check("deleting a user keeps their records, recorded_by_id -> NULL (PostgreSQL)",
                  kept is not None and kept.recorded_by_id is None)
            db.session.delete(kept)
            db.session.commit()

    # -------------------------------------------------------- authorization
    section("4. Authorization")
    base = "/api/dogs/4/medical"
    for path in ("", "/records", "/vaccinations", "/medications", "/observations", "/follow-ups"):
        check(f"anonymous GET {base}{path} -> 401", client.get(base + path).status_code == 401)
    ok_follow_up = {"reason": "Recheck", "due_date": str(today + timedelta(days=7)), "status": "pending"}
    check("anonymous POST -> 401", client.post(f"{base}/follow-ups", json=ok_follow_up).status_code == 401)
    check("signed-in user can read the summary", client.get(base, headers=user).status_code == 200)
    check("signed-in user can read a list", client.get(f"{base}/medications", headers=user).status_code == 200)
    check("signed-in user POST -> 403",
          client.post(f"{base}/follow-ups", json=ok_follow_up, headers=user).status_code == 403)
    check("signed-in user PATCH -> 403",
          client.patch(f"{base}/follow-ups/1", json={"notes": "x"}, headers=user).status_code == 403)
    check("DELETE is not offered (405)",
          client.delete(f"{base}/follow-ups/1", headers=admin).status_code == 405)
    check("forged token -> 401",
          client.get(base, headers={"Authorization": "Bearer not.a.token"}).status_code == 401)
    throwaway = login("demo@dogo-paw.org", "demo123")
    client.post("/api/auth/logout", headers=throwaway)
    check("revoked token -> 401", client.get(base, headers=throwaway).status_code == 401)

    # ------------------------------------------------------------------ CRUD
    section("5. Create, read, update")
    d = lambda days: str(today - timedelta(days=days))  # noqa: E731
    valid = {
        "records": {"record_type": "checkup", "title": "Annual check", "veterinarian": "Dr. X",
                    "visit_date": d(1), "description": "All normal."},
        "vaccinations": {"vaccine_name": "Rabies", "administered_date": d(2),
                         "next_due_date": str(today + timedelta(days=365)), "status": "completed"},
        "medications": {"medication_name": "Drug A", "dosage": "5 mg", "frequency": "daily",
                        "start_date": d(3), "status": "active"},
        "observations": {"observation_date": d(0), "weight_kg": 12.5, "temperature_c": 38.6,
                         "symptoms": ["Cough", "cough", " sneezing "]},
        "follow-ups": ok_follow_up,
    }
    created = {}
    for kind, body in valid.items():
        response = client.post(f"/api/dogs/3/medical/{kind}", json=body, headers=admin)
        check(f"admin POST {kind} -> 201", response.status_code == 201, response.get_json())
        created[kind] = response.get_json().get("item", {})
        listed = client.get(f"/api/dogs/3/medical/{kind}", headers=user).get_json()
        check(f"GET {kind} returns it", any(i["id"] == created[kind].get("id") for i in listed["items"]))
    check("symptoms normalised and de-duplicated", created["observations"].get("symptoms") == ["cough", "sneezing"])
    check("dates round-trip as YYYY-MM-DD", created["records"].get("visit_date") == d(1))
    check("dog_id in body is ignored",
          client.post("/api/dogs/3/medical/follow-ups", json={**ok_follow_up, "dog_id": 1},
                      headers=admin).get_json()["item"]["dog_id"] == 3)

    summary = client.get("/api/dogs/3/medical", headers=user).get_json()
    check("summary has the expected sections", set(summary) == {
        "dog", "vaccinations", "medications", "recent_observations", "follow_ups",
        "recent_medical_records", "counts"}, sorted(summary))
    check("summary dog is the plain profile", set(summary["dog"]) == DOG_KEYS)
    check("summary counts", summary["counts"] == {
        "medical_records": 1, "vaccinations": 1, "medications": 1,
        "health_observations": 1, "follow_ups": 2}, summary["counts"])
    check("summary carries no score or health label",
          not {"risk", "score", "healthy", "status", "health_status"} & set(summary))
    rocky = client.get("/api/dogs/4/medical", headers=user).get_json()
    check("summary limits recent observations to 10", len(rocky["recent_observations"]) <= medical.SUMMARY_RECENT)

    fu = created["follow-ups"]["id"]
    r = client.patch(f"/api/dogs/3/medical/follow-ups/{fu}", json={"status": "completed"}, headers=admin)
    check("PATCH completed without completed_date -> 400", r.status_code == 400, r.get_json())
    r = client.patch(f"/api/dogs/3/medical/follow-ups/{fu}",
                     json={"status": "completed", "completed_date": d(0)}, headers=admin)
    check("PATCH follow-up to completed -> 200", r.status_code == 200 and r.get_json()["item"]["status"] == "completed")
    ob = created["observations"]["id"]
    r = client.patch(f"/api/dogs/3/medical/observations/{ob}", json={"weight_kg": 12.9}, headers=admin)
    check("PATCH corrects an observation", r.status_code == 200 and r.get_json()["item"]["weight_kg"] == 12.9)
    check("PATCH another dog's record -> 404",
          client.patch(f"/api/dogs/4/medical/observations/{ob}", json={"weight_kg": 1}, headers=admin).status_code == 404)
    check("PATCH setting a required field to null -> 400",
          client.patch(f"/api/dogs/3/medical/follow-ups/{fu}", json={"reason": None}, headers=admin).status_code == 400)
    check("PATCH with no editable fields -> 400",
          client.patch(f"/api/dogs/3/medical/follow-ups/{fu}", json={"id": 5}, headers=admin).status_code == 400)

    # ------------------------------------------------------------ validation
    section("6. Validation")

    def rejects(kind, body, label, dog=3, status=400):
        r = client.post(f"/api/dogs/{dog}/medical/{kind}", json=body, headers=admin)
        check(f"{label} -> {status}", r.status_code == status, (r.status_code, r.get_json()))

    rejects("follow-ups", ok_follow_up, "unknown dog", dog=9999, status=404)
    check("GET for unknown dog -> 404", client.get("/api/dogs/9999/medical", headers=user).status_code == 404)
    rejects("allergies", {}, "unknown record type", status=404)
    for bad in ("2026-13-01", "2026-02-30", "yesterday", "01/10/2026", 20260101, "1900-01-01"):
        rejects("follow-ups", {**ok_follow_up, "due_date": bad}, f"invalid date {bad!r}")
    rejects("records", {**valid["records"], "visit_date": str(today + timedelta(days=30))}, "future visit_date")
    rejects("observations", {**valid["observations"], "observation_date": str(today + timedelta(days=5))},
            "future observation_date")
    rejects("follow-ups", {**ok_follow_up, "status": "done"}, "invalid follow-up status")
    rejects("vaccinations", {**valid["vaccinations"], "status": "given"}, "invalid vaccination status")
    rejects("medications", {**valid["medications"], "status": "paused"}, "invalid medication status")
    rejects("records", {**valid["records"], "record_type": "consult"}, "invalid record_type")
    for weight in (-3, 0, 121, "12", True):
        rejects("observations", {"observation_date": d(0), "weight_kg": weight}, f"weight {weight!r}")
    for temp in (29.9, 45.1, 101.5):
        rejects("observations", {"observation_date": d(0), "temperature_c": temp}, f"temperature {temp}")
    check("temperature bounds are inclusive (30.0 and 45.0 accepted)", all(
        client.post("/api/dogs/3/medical/observations", headers=admin,
                    json={"observation_date": d(0), "temperature_c": t}).status_code == 201
        for t in (30.0, 45.0)))
    rejects("observations", {"observation_date": d(0)}, "observation with no measurement")
    rejects("observations", {"observation_date": d(0), "symptoms": "cough"}, "symptoms not a list")
    rejects("observations", {"observation_date": d(0), "symptoms": [""]}, "empty symptom")
    for field in ("vaccine_name", "status"):
        rejects("vaccinations", {k: v for k, v in valid["vaccinations"].items() if k != field}, f"missing {field}")
    rejects("vaccinations", {**valid["vaccinations"], "vaccine_name": "   "}, "blank vaccine_name")
    for field in ("medication_name", "dosage", "frequency", "start_date"):
        rejects("medications", {k: v for k, v in valid["medications"].items() if k != field}, f"missing {field}")
    for field in ("reason", "due_date"):
        rejects("follow-ups", {k: v for k, v in ok_follow_up.items() if k != field}, f"missing follow-up {field}")
    rejects("records", {**valid["records"], "title": "x" * 161}, "title over 160 characters")
    rejects("records", {**valid["records"], "title": {"$ne": None}}, "non-string title")
    rejects("vaccinations", {"vaccine_name": "DHPP", "status": "completed"}, "completed vaccination without date")
    rejects("vaccinations", {"vaccine_name": "DHPP", "status": "scheduled"}, "scheduled vaccination without due date")
    rejects("vaccinations", {**valid["vaccinations"], "next_due_date": d(10)}, "next_due_date before administered")
    rejects("medications", {**valid["medications"], "end_date": d(10)}, "end_date before start_date")
    rejects("medications", {**valid["medications"], "status": "completed"}, "completed medication without end_date")
    rejects("follow-ups", {**ok_follow_up, "completed_date": d(0)}, "completed_date on a pending follow-up")
    r = client.post("/api/dogs/3/medical/follow-ups", data="[1,2]", content_type="application/json", headers=admin)
    check("JSON array body -> 400", r.status_code == 400)
    r = client.post("/api/dogs/3/medical/follow-ups", data="not json", content_type="application/json", headers=admin)
    check("malformed JSON -> 400", r.status_code == 400)

    # ------------------------------------------------------------ regression
    section("7. Existing dog API unchanged")
    dogs = client.get("/api/dogs").get_json()
    check("GET /api/dogs still public, 18 dogs", dogs["count"] == 18)
    check("GET /api/dogs rows carry only profile keys", all(set(x) == DOG_KEYS for x in dogs["dogs"]))
    one = client.get("/api/dogs/4")
    check("GET /api/dogs/4 still public, profile only",
          one.status_code == 200 and set(one.get_json()) == {"dog"} and set(one.get_json()["dog"]) == DOG_KEYS)

    # ------------------------------------------------------------- rollback
    section("8. Migration rollback and re-apply")
    with app.app_context():
        before = {t: db.session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in BASELINE_TABLES}
        # End the read transaction first: on PostgreSQL its lock on `dogs`
        # would block the DROP TABLE of a table that references it.
        db.session.remove()
        downgrade(revision="0001_baseline")
        db.session.remove()
        tables = set(inspect(db.engine).get_table_names())
        check("downgrade removes only the medical tables", not (MEDICAL_TABLES & tables) and BASELINE_TABLES <= tables)
        after = {t: db.session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in BASELINE_TABLES}
        check("downgrade keeps every baseline row", before == after, (before, after))
        db.session.remove()
        upgrade()
        db.session.remove()
        tables = set(inspect(db.engine).get_table_names())
        check("upgrade re-creates the medical tables", MEDICAL_TABLES <= tables)
        check("medical tables start empty after re-apply",
              db.session.execute(text("SELECT COUNT(*) FROM follow_ups")).scalar() == 0)


# --------------------------------------------------------------------------- #
def child(url: str) -> int:
    os.environ.update(DATABASE_URL=url, APP_ENV="development", RATE_LIMIT_ENABLED="false")
    run_checks()
    print(f"\n{'all passed' if not FAILURES else f'{len(FAILURES)} FAILED: {FAILURES}'}")
    return 1 if FAILURES else 0


def spawn(url: str) -> int:
    try:
        return subprocess.run(
            [sys.executable, __file__, "--child", url], cwd=HERE,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"}, timeout=300,
        ).returncode
    except subprocess.TimeoutExpired:
        # A migration waiting on a lock hangs rather than failing; make it fail.
        print("  [FAIL] timed out after 300s (likely a migration blocked on a lock)")
        return 1


def main() -> int:
    if "--child" in sys.argv:
        return child(sys.argv[sys.argv.index("--child") + 1])

    pg_url = sys.argv[sys.argv.index("--postgres") + 1] if "--postgres" in sys.argv else None
    if pg_url:
        from sqlalchemy.engine import make_url

        host = make_url(pg_url).host
        if host not in LOCAL_HOSTS:
            print(f"refusing to run against {host!r}: --postgres must be a local, disposable database")
            return 2

    with tempfile.TemporaryDirectory() as tmp:
        print("=== SQLite ===")
        code = spawn(f"sqlite:///{Path(tmp) / 'medical.db'}")

    if pg_url:
        from sqlalchemy import create_engine, text

        engine = create_engine(pg_url.replace("postgresql://", "postgresql+psycopg://", 1))

        def reset():
            with engine.begin() as c:
                c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))

        print("\n=== PostgreSQL ===")
        reset()
        code = spawn(pg_url) or code
        reset()
        engine.dispose()

    return code


if __name__ == "__main__":
    sys.exit(main())
