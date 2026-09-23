"""
Checks for the health alert workflow (health_alerts.py, notification_service.py).

Alerts are driven through the real API and the real engine; the medical records
behind them are edited directly so each scenario produces exactly the findings
it needs. Dates are offsets from today, because the sync endpoint evaluates
against the current date. (Determinism against a frozen date is covered by
test_health_intelligence.py.)

    python test_health_alerts.py
    python test_health_alerts.py --postgres postgresql://postgres@127.0.0.1:5432/scratch

The --postgres URL must be a local, EMPTY, disposable database: its public
schema is dropped and recreated.
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
HEAD = "0004_dog_id_sequence"
ALERT_TABLES = {"health_alerts", "notifications"}
KEPT_TABLES = {"medical_records", "vaccinations", "medications", "health_observations",
               "follow_ups", "dogs", "users"}
TODAY = date.today()
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: object = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f"  ({detail})" if detail != "" and not condition else ""))
    if not condition:
        FAILURES.append(label)


def section(title: str) -> None:
    print(f"\n{title}")


def ago(days: int) -> date:
    return TODAY - timedelta(days=days)


def ahead(days: int) -> date:
    return TODAY + timedelta(days=days)


def run_checks() -> None:
    import app as app_module
    from flask_migrate import downgrade, upgrade
    from sqlalchemy import inspect, text
    from sqlalchemy.exc import IntegrityError

    import health_alerts
    import notification_service as ns
    from models import (
        Dog, FollowUp, HealthAlert, HealthObservation, Medication, Notification, User, db,
    )

    app = app_module.app
    client = app.test_client()

    def login(email, password):
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        return {"Authorization": f"Bearer {r.json['token']}"}

    admin, user = login("admin@dogo-paw.org", "admin123"), login("demo@dogo-paw.org", "demo123")

    # Each scenario gets its own dog, so nothing interferes with anything else.
    def fresh_dog(dog_id: int, name: str) -> int:
        with app.app_context():
            if db.session.get(Dog, dog_id) is None:
                db.session.add(Dog(id=dog_id, name=name, age=3, energy_level="low",
                                   size="small", temperament="calm"))
                db.session.commit()
        return dog_id

    def add(*rows):
        with app.app_context():
            db.session.add_all(rows)
            db.session.commit()

    def sync(dog_id: int, as_admin=True):
        return client.post(f"/api/dogs/{dog_id}/medical/health-alerts/sync",
                           headers=admin if as_admin else user)

    def sync_json(dog_id: int) -> dict:
        return sync(dog_id).get_json()

    def alerts_of(dog_id: int, status=None) -> list[dict]:
        with app.app_context():
            q = HealthAlert.query.filter_by(dog_id=dog_id)
            if status:
                q = q.filter_by(status=status)
            return [a.to_dict() for a in q.order_by(HealthAlert.id).all()]

    def codes(dog_id: int, status=None) -> set:
        return {a["finding_code"] for a in alerts_of(dog_id, status)}

    # ------------------------------------------------------------ schema
    section("1. Schema and migration")
    with app.app_context():
        insp = inspect(db.engine)
        tables = set(insp.get_table_names())
        check("health_alerts and notifications exist", ALERT_TABLES <= tables, ALERT_TABLES - tables)
        version = db.session.execute(text("SELECT version_num FROM alembic_version")).scalar()
        check(f"database is at {HEAD}", version == HEAD, version)

        fks = {(tuple(f["constrained_columns"]), f["referred_table"], f.get("options", {}).get("ondelete"))
               for f in insp.get_foreign_keys("health_alerts")}
        check("dog_id -> dogs CASCADE", (("dog_id",), "dogs", "CASCADE") in fks, fks)
        check("acknowledged_by_id -> users SET NULL",
              (("acknowledged_by_id",), "users", "SET NULL") in fks, fks)
        check("resolved_by_id -> users SET NULL",
              (("resolved_by_id",), "users", "SET NULL") in fks, fks)
        check("reopened_from_id -> health_alerts SET NULL",
              (("reopened_from_id",), "health_alerts", "SET NULL") in fks, fks)
        index_names = {i["name"] for i in insp.get_indexes("health_alerts")}
        check("partial unique identity index exists",
              "uq_health_alerts_active_identity" in index_names, index_names)
        check("status and severity are indexed",
              {"ix_health_alerts_status", "ix_health_alerts_severity"} <= index_names)

        def rejected(row) -> bool:
            db.session.add(row)
            try:
                db.session.commit()
                return False
            except IntegrityError:
                db.session.rollback()
                return True

        base = dict(dog_id=1, category="follow_up", finding_code="x", entity_key="",
                    title="t", reason="r", risk_score_at_detection=10)
        check("CHECK rejects an unknown status",
              rejected(HealthAlert(**base, severity="high", status="snoozed")))
        check("CHECK rejects an unknown severity",
              rejected(HealthAlert(**base, severity="urgent", status="open")))
        check("CHECK rejects an unknown notification status",
              rejected(Notification(event_type="health_alert", status="queued")))

    # -------------------------------------------------- creation and content
    section("2. Alert creation")
    d1 = fresh_dog(9101, "Alpha")
    check("no findings -> no alerts", sync_json(d1)["created"] == 0 and not alerts_of(d1))

    add(FollowUp(dog_id=d1, reason="Missed recheck", due_date=ago(30), status="missed"))
    r = sync_json(d1)
    check("one finding -> one alert", (r["created"], len(alerts_of(d1))) == (1, 1), r)
    alert = alerts_of(d1)[0]
    check("severity comes from the finding", alert["severity"] == "high", alert["severity"])
    check("category and finding_code copied", (alert["category"], alert["finding_code"])
          == ("follow_up", "follow_up.missed"))
    check("evidence preserved", alert["evidence"].get("due_date") == ago(30).isoformat())
    check("entity_key identifies the source record",
          alert["entity_key"].startswith("follow_up_id:"), alert["entity_key"])
    check("risk score snapshot recorded", alert["risk_score_at_detection"] == r["risk_score"])
    check("starts open, detected once",
          (alert["status"], alert["detection_count"]) == ("open", 1))
    check("recommendation and reason stored", alert["recommendation"] and alert["reason"])
    check("timestamps set", alert["first_detected_at"] and alert["last_detected_at"])

    add(Medication(dog_id=d1, medication_name="Old drug", dosage="1", frequency="daily",
                   start_date=ago(400), status="active"),
        HealthObservation(dog_id=d1, observation_date=ago(40), weight_kg=20.0),
        HealthObservation(dog_id=d1, observation_date=ago(3), weight_kg=17.0))
    r = sync_json(d1)
    check("multiple findings -> multiple alerts", r["created"] >= 2, r)
    severities = {a["severity"] for a in alerts_of(d1)}
    check("severities span more than one level", len(severities) > 1, severities)
    check("each alert has its own identity",
          len({(a["finding_code"], a["entity_key"]) for a in alerts_of(d1)}) == len(alerts_of(d1)))

    # ------------------------------------------------------- deduplication
    section("3. Deduplication and idempotency")
    before = alerts_of(d1)
    results = [sync_json(d1) for _ in range(5)]
    after = alerts_of(d1)
    check("five more syncs create nothing", all(x["created"] == 0 for x in results), results[0])
    check("alert count unchanged", len(after) == len(before), (len(before), len(after)))
    check("alert ids unchanged", [a["id"] for a in after] == [a["id"] for a in before])
    check("updated count matches the live findings",
          all(x["updated"] == len(before) for x in results))
    check("detection_count increased by five",
          after[0]["detection_count"] == before[0]["detection_count"] + 5,
          (before[0]["detection_count"], after[0]["detection_count"]))
    check("first_detected_at never moves",
          [a["first_detected_at"] for a in after] == [a["first_detected_at"] for a in before])
    check("risk snapshot never moves",
          [a["risk_score_at_detection"] for a in after]
          == [a["risk_score_at_detection"] for a in before])

    with app.app_context():
        # The database itself refuses a second active alert for one identity,
        # which is what protects against two syncs running at once.
        existing = HealthAlert.query.filter_by(dog_id=d1).first()
        duplicate = HealthAlert(
            dog_id=existing.dog_id, category=existing.category,
            finding_code=existing.finding_code, entity_key=existing.entity_key,
            severity="high", title="dup", reason="dup", risk_score_at_detection=1, status="open")
        db.session.add(duplicate)
        try:
            db.session.commit()
            duplicated = False
        except IntegrityError:
            db.session.rollback()
            duplicated = True
        check("database rejects a second active alert for the same finding", duplicated)

    # --------------------------------------------------------- disappearing
    section("4. Finding disappears, then returns")
    d2 = fresh_dog(9102, "Bravo")
    add(FollowUp(dog_id=d2, reason="Temporary", due_date=ago(20), status="missed"),
        FollowUp(dog_id=d2, reason="Other", due_date=ago(25), status="missed"))
    sync_json(d2)
    check("two alerts raised", len(alerts_of(d2)) == 2)

    with app.app_context():
        row = FollowUp.query.filter_by(dog_id=d2, reason="Temporary").first()
        temporary_id = row.id
        row.status = "completed"
        row.completed_date = ago(1)
        db.session.commit()
    r = sync_json(d2)
    check("finding gone -> its alert auto-resolves", r["resolved"] == 1, r)
    closed = [a for a in alerts_of(d2) if a["status"] == "resolved"]
    check("auto-resolved alert is flagged and explained",
          len(closed) == 1 and closed[0]["auto_resolved"] and closed[0]["resolution_note"])
    check("auto-resolution records no user", closed[0]["resolved_by_id"] is None)
    check("resolved alert keeps its evidence and history",
          closed[0]["evidence"] and closed[0]["first_detected_at"])
    check("nothing is deleted", len(alerts_of(d2)) == 2)
    check("the unrelated alert is untouched",
          [a["status"] for a in alerts_of(d2) if a["finding_code"] == "follow_up.missed"
           and a["id"] != closed[0]["id"]] == ["open"])

    with app.app_context():
        row = db.session.get(FollowUp, temporary_id)
        row.status = "missed"
        row.completed_date = None
        db.session.commit()
    r = sync_json(d2)
    check("finding returns -> reopened, not created", (r["reopened"], r["created"]) == (1, 0), r)
    chain = [a for a in alerts_of(d2) if a["reopened_from_id"]]
    check("the new alert links back to the resolved one",
          len(chain) == 1 and chain[0]["reopened_from_id"] == closed[0]["id"])
    check("the old resolved alert is unchanged",
          [a for a in alerts_of(d2) if a["id"] == closed[0]["id"]][0]["resolution_note"]
          == closed[0]["resolution_note"])
    check("history is kept: three rows for two findings", len(alerts_of(d2)) == 3)

    # A deleted source record removes the finding too.
    d3 = fresh_dog(9103, "Charlie")
    add(FollowUp(dog_id=d3, reason="To delete", due_date=ago(20), status="missed"))
    sync_json(d3)
    with app.app_context():
        db.session.delete(FollowUp.query.filter_by(dog_id=d3).first())
        db.session.commit()
    r = sync_json(d3)
    check("deleting the source record auto-resolves its alert",
          r["resolved"] == 1 and alerts_of(d3)[0]["status"] == "resolved")

    # ------------------------------------------------------------ severity
    section("5. Severity changes and the risk snapshot")
    d4 = fresh_dog(9104, "Delta")
    with app.app_context():
        db.session.add(FollowUp(dog_id=d4, reason="Drifting", due_date=ago(3), status="pending"))
        db.session.commit()
    sync_json(d4)
    check("overdue by 3 days -> moderate", alerts_of(d4)[0]["severity"] == "moderate")
    original_score = alerts_of(d4)[0]["risk_score_at_detection"]
    with app.app_context():
        FollowUp.query.filter_by(dog_id=d4).first().due_date = ago(40)
        db.session.commit()
    r = sync_json(d4)
    check("same alert updated, not duplicated", (r["created"], r["updated"]) == (0, 1))
    check("severity follows the finding", alerts_of(d4)[0]["severity"] == "high")
    check("risk snapshot stays at detection time",
          alerts_of(d4)[0]["risk_score_at_detection"] == original_score)
    check("reason and evidence refreshed",
          alerts_of(d4)[0]["evidence"]["days_overdue"] == 40)

    # ----------------------------------------------------------- lifecycle
    section("6. Admin lifecycle")
    d5 = fresh_dog(9105, "Echo")
    add(FollowUp(dog_id=d5, reason="Lifecycle", due_date=ago(30), status="missed"))
    sync_json(d5)
    alert_id = alerts_of(d5)[0]["id"]
    url = f"/api/admin/health-alerts/{alert_id}"

    r = client.patch(url, json={"action": "acknowledge"}, headers=admin)
    body = r.get_json()["alert"]
    check("acknowledge -> 200, status acknowledged",
          r.status_code == 200 and body["status"] == "acknowledged")
    check("acknowledged_at and acknowledged_by_id set",
          body["acknowledged_at"] and body["acknowledged_by_id"] and body["acknowledged_by"])
    check("acknowledging twice -> 409",
          client.patch(url, json={"action": "acknowledge"}, headers=admin).status_code == 409)
    check("an acknowledged alert is still active and still synced",
          sync_json(d5)["updated"] == 1 and alerts_of(d5)[0]["status"] == "acknowledged")

    r = client.patch(url, json={"action": "resolve", "resolution_note": "Vet visit booked."},
                     headers=admin)
    body = r.get_json()["alert"]
    check("resolve -> 200, status resolved", r.status_code == 200 and body["status"] == "resolved")
    check("resolved_at and resolved_by_id set", body["resolved_at"] and body["resolved_by_id"])
    check("resolution note preserved", body["resolution_note"] == "Vet visit booked.")
    check("manual resolution is not flagged automatic", body["auto_resolved"] is False)
    check("acknowledgement history survives resolution",
          body["acknowledged_by_id"] and body["acknowledged_at"])
    check("resolving twice -> 409",
          client.patch(url, json={"action": "resolve"}, headers=admin).status_code == 409)
    check("acknowledging a resolved alert -> 409",
          client.patch(url, json={"action": "acknowledge"}, headers=admin).status_code == 409)

    r = sync_json(d5)
    check("a finding still present after manual resolve comes back as a new alert",
          r["reopened"] == 1 and len(alerts_of(d5)) == 2, r)
    check("the resolved row is left intact",
          [a for a in alerts_of(d5) if a["id"] == alert_id][0]["resolution_note"]
          == "Vet visit booked.")

    check("unknown action -> 400",
          client.patch(url, json={"action": "snooze"}, headers=admin).status_code == 400)
    check("missing action -> 400", client.patch(url, json={}, headers=admin).status_code == 400)
    check("non-object body -> 400",
          client.patch(url, data="[1]", content_type="application/json",
                       headers=admin).status_code == 400)
    check("over-long resolution note -> 400", client.patch(
        f"/api/admin/health-alerts/{alerts_of(d5)[-1]['id']}",
        json={"action": "resolve", "resolution_note": "x" * 1001}, headers=admin).status_code == 400)
    check("unknown alert -> 404",
          client.patch("/api/admin/health-alerts/999999", json={"action": "resolve"},
                       headers=admin).status_code == 404)

    # ------------------------------------------------------- authorization
    section("7. Authorization")
    check("anonymous sync -> 401", client.post(f"/api/dogs/{d5}/medical/health-alerts/sync").status_code == 401)
    check("normal user sync -> 403", sync(d5, as_admin=False).status_code == 403)
    check("anonymous dog alerts -> 401",
          client.get(f"/api/dogs/{d5}/medical/health-alerts").status_code == 401)
    check("normal user can read dog alerts -> 200",
          client.get(f"/api/dogs/{d5}/medical/health-alerts", headers=user).status_code == 200)
    check("anonymous admin queue -> 401", client.get("/api/admin/health-alerts").status_code == 401)
    check("normal user admin queue -> 403",
          client.get("/api/admin/health-alerts", headers=user).status_code == 403)
    check("normal user cannot acknowledge -> 403",
          client.patch(url, json={"action": "acknowledge"}, headers=user).status_code == 403)
    throwaway = login("demo@dogo-paw.org", "demo123")
    client.post("/api/auth/logout", headers=throwaway)
    check("revoked token -> 401",
          client.get(f"/api/dogs/{d5}/medical/health-alerts", headers=throwaway).status_code == 401)
    check("sync for an unknown dog -> 404",
          client.post("/api/dogs/9999/medical/health-alerts/sync", headers=admin).status_code == 404)
    check("alerts for an unknown dog -> 404",
          client.get("/api/dogs/9999/medical/health-alerts", headers=admin).status_code == 404)

    # ---------------------------------------------------------------- reads
    section("8. Reading alerts")
    body = client.get(f"/api/dogs/{d5}/medical/health-alerts", headers=user).get_json()
    check("grouped by status", {"open", "acknowledged", "resolved"} <= set(body))
    check("counts match the groups",
          all(body["counts"][k] == len(body[k]) for k in ("open", "acknowledged", "resolved")))
    check("resolved history is visible", len(body["resolved"]) >= 1)
    filtered = client.get(f"/api/dogs/{d5}/medical/health-alerts?status=resolved",
                          headers=user).get_json()
    check("status filter narrows the result",
          filtered["count"] == len(body["resolved"]) and not filtered["open"])
    check("invalid status filter -> 400",
          client.get(f"/api/dogs/{d5}/medical/health-alerts?status=bogus",
                     headers=user).status_code == 400)

    queue = client.get("/api/admin/health-alerts", headers=admin).get_json()
    check("admin queue returns alerts across dogs",
          len({a["dog_id"] for a in queue["alerts"]}) > 1, queue["count"])
    check("queue is ordered by severity, worst first",
          [a["severity"] for a in queue["alerts"]] == sorted(
              [a["severity"] for a in queue["alerts"]],
              key=lambda s: -health_alerts.SEVERITY_ORDER.index(s)))
    check("queue carries the dog name", all("dog_name" in a for a in queue["alerts"]))
    # The dashboard header reads these rather than counting a truncated page.
    totals = queue["totals"]
    check("queue reports totals by status",
          {"open", "acknowledged", "resolved", "total"} <= set(totals), totals)
    with app.app_context():
        check("totals match the table",
              totals["total"] == HealthAlert.query.count()
              and totals["open"] == HealthAlert.query.filter_by(status="open").count(),
              totals)
        check("active severity counts exclude resolved alerts",
              sum(totals["active_by_severity"].values())
              == HealthAlert.query.filter(HealthAlert.status.in_(("open", "acknowledged"))).count(),
              totals["active_by_severity"])
    check("totals ignore the current filters",
          client.get("/api/admin/health-alerts?severity=low",
                     headers=admin).get_json()["totals"] == totals)
    one_dog = client.get(f"/api/admin/health-alerts?dog_id={d5}", headers=admin).get_json()
    check("dog_id filter", {a["dog_id"] for a in one_dog["alerts"]} == {d5})
    high = client.get("/api/admin/health-alerts?severity=high,critical", headers=admin).get_json()
    check("severity filter accepts a comma-separated list",
          {a["severity"] for a in high["alerts"]} <= {"high", "critical"})
    open_only = client.get("/api/admin/health-alerts?status=open", headers=admin).get_json()
    check("status filter", {a["status"] for a in open_only["alerts"]} == {"open"})
    check("limit is applied",
          client.get("/api/admin/health-alerts?limit=1", headers=admin).get_json()["count"] >= 1
          and len(client.get("/api/admin/health-alerts?limit=1",
                             headers=admin).get_json()["alerts"]) == 1)
    check("invalid severity filter -> 400",
          client.get("/api/admin/health-alerts?severity=nope", headers=admin).status_code == 400)
    check("invalid dog_id filter -> 400",
          client.get("/api/admin/health-alerts?dog_id=abc", headers=admin).status_code == 400)

    # Listing alerts must not cost one query per alert. Every row reports its
    # dog's name and its reviewer, and leaving those lazy made the queue issue
    # a round trip per row — the regression this guards.
    from sqlalchemy import event as sa_event

    with app.app_context():
        counter = {"n": 0}

        def count(*_args):
            counter["n"] += 1

        sa_event.listen(db.engine, "before_cursor_execute", count)
        try:
            counter["n"] = 0
            client.get("/api/admin/health-alerts?limit=200", headers=admin)
            queries = counter["n"]
            total = HealthAlert.query.count()
        finally:
            sa_event.remove(db.engine, "before_cursor_execute", count)

    check("the alert queue does not issue a query per alert",
          queries < 10, f"{queries} queries for {total} alerts")
    check("the queue still returns the alerts it loaded eagerly",
          len(client.get("/api/admin/health-alerts?limit=200", headers=admin)
              .get_json()["alerts"]) > 1)
    check("eager loading does not lose the dog name",
          all(a["dog_name"] for a in
              client.get("/api/admin/health-alerts?limit=200", headers=admin)
              .get_json()["alerts"]))

    # -------------------------------------------------------- notifications
    section("9. Notification outbox")
    with app.app_context():
        rows = Notification.query.all()
        check("notifications were queued", len(rows) > 0)
        check("every row is pending and undelivered",
              all(n.status == "pending" and n.delivered_at is None for n in rows))
        check("every row is internal", all(n.channel == "internal" for n in rows))
        check("payload carries the event details", all(
            {"type", "event", "dog_id", "alert_id", "severity"} <= set(n.payload) for n in rows))
        check("only moderate and above are notified",
              all(n.severity in ("moderate", "high", "critical") for n in rows),
              {n.severity for n in rows})
        check("events are creations, recurrences or escalations",
              {n.payload["event"] for n in rows} <= {"created", "reopened", "escalated"},
              {n.payload["event"] for n in rows})
        check("pending() returns what a sender would read", len(ns.pending()) == len(rows))
        check("a low-severity finding raises no notification",
              not ns.should_notify("created", "low"))
        check("an alert seen again raises no notification",
              not ns.should_notify("updated", "critical"))
        check("every notification points at a real alert",
              all(db.session.get(HealthAlert, n.alert_id) is not None for n in rows))
        escalations = [n for n in rows if n.payload["event"] == "escalated"]
        check("the escalation recorded its previous severity",
              bool(escalations) and all("previous_severity" in n.payload for n in escalations))

    # ------------------------------------------------------------- privacy
    section("10. Privacy and regression")
    dogs = client.get("/api/dogs").get_json()
    check("GET /api/dogs still public and unchanged",
          dogs["count"] >= 18 and all(
              not {"alerts", "risk_score", "health_alerts"} & set(d) for d in dogs["dogs"]))
    one = client.get("/api/dogs/4").get_json()["dog"]
    check("GET /api/dogs/<id> carries no alert data",
          not {"alerts", "risk_score", "health_alerts"} & set(one))
    check("medical summary is unchanged",
          set(client.get("/api/dogs/4/medical", headers=user).get_json()) == {
              "dog", "vaccinations", "medications", "recent_observations",
              "follow_ups", "recent_medical_records", "counts"})
    check("health analysis still works and is unchanged in shape",
          {"risk_level", "risk_score", "findings", "data_quality"}
          <= set(client.get("/api/dogs/4/medical/health-analysis", headers=user).get_json()))
    check("record-type routes still work",
          client.get(f"/api/dogs/{d5}/medical/follow-ups", headers=user).status_code == 200)

    # Phase 4 must be usable on its own, with no alerts written.
    with app.app_context():
        import health_intelligence
        d6 = 9106
        if db.session.get(Dog, d6) is None:
            db.session.add(Dog(id=d6, name="Foxtrot", age=2, energy_level="low",
                               size="small", temperament="calm"))
            db.session.commit()
        dog = db.session.get(Dog, d6)
        analysis = health_intelligence.analyse_dog(dog, today=TODAY)
        check("the engine still runs without touching alerts",
              "risk_score" in analysis and HealthAlert.query.filter_by(dog_id=d6).count() == 0)

    # ------------------------------------------------- migration up/down/up
    section("11. Migration rollback and re-apply")
    with app.app_context():
        kept_before = {t: db.session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                       for t in KEPT_TABLES}
        alerts_before = db.session.execute(text("SELECT COUNT(*) FROM health_alerts")).scalar()
        check("there are alerts to lose", alerts_before > 0)
        db.session.remove()
        downgrade(revision="0002_medical_foundation")
        db.session.remove()
        tables = set(inspect(db.engine).get_table_names())
        check("downgrade drops only the alert tables",
              not (ALERT_TABLES & tables) and KEPT_TABLES <= tables)
        kept_after = {t: db.session.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
                      for t in KEPT_TABLES}
        check("every medical and baseline row survives", kept_before == kept_after,
              (kept_before, kept_after))
        db.session.remove()
        upgrade()
        db.session.remove()
        check("upgrade re-creates the alert tables",
              ALERT_TABLES <= set(inspect(db.engine).get_table_names()))
        check("alert tables come back empty",
              db.session.execute(text("SELECT COUNT(*) FROM health_alerts")).scalar() == 0)

    # Sync still works after the round trip.
    r = sync_json(d5)
    check("sync works again after re-applying the migration", r["created"] >= 1, r)


def main() -> int:
    if "--child" in sys.argv:
        run_checks()
        print(f"\n{'all passed' if not FAILURES else f'{len(FAILURES)} FAILED: {FAILURES}'}")
        return 1 if FAILURES else 0

    pg_url = sys.argv[sys.argv.index("--postgres") + 1] if "--postgres" in sys.argv else None
    if pg_url:
        from sqlalchemy.engine import make_url

        if make_url(pg_url).host not in LOCAL_HOSTS:
            print(f"refusing to run against {make_url(pg_url).host!r}: local databases only")
            return 2

    def spawn(url: str) -> int:
        try:
            return subprocess.run(
                [sys.executable, __file__, "--child"], cwd=HERE,
                env={**os.environ, "DATABASE_URL": url, "APP_ENV": "development",
                     "RATE_LIMIT_ENABLED": "false", "PYTHONIOENCODING": "utf-8"},
                timeout=600,
            ).returncode
        except subprocess.TimeoutExpired:
            print("  [FAIL] timed out (a migration may be blocked on a lock)")
            return 1

    with tempfile.TemporaryDirectory() as tmp:
        print("=== SQLite ===")
        code = spawn(f"sqlite:///{Path(tmp) / 'alerts.db'}")

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
