"""
Checks for the health intelligence engine (health_intelligence.py).

Most of it needs no database: the rules are pure functions over model objects,
so they are driven directly with a fixed `today`, which makes every expected
value exact rather than relative to the day the suite runs. The API section at
the end uses a throwaway SQLite database.

    python test_health_intelligence.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILURES: list[str] = []

TODAY = date(2026, 9, 1)  # fixed: every expectation below is relative to this


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
    import health_intelligence as hi
    from models import Dog, FollowUp, HealthObservation, MedicalRecord, Medication, Vaccination

    dog = Dog(id=1, name="Test")

    def analyse(**kwargs):
        """Analyse one dog, with every record type defaulting to empty."""
        return hi.analyse(
            dog,
            vaccinations=kwargs.get("vaccinations", []),
            medications=kwargs.get("medications", []),
            observations=kwargs.get("observations", []),
            follow_ups=kwargs.get("follow_ups", []),
            records=kwargs.get("records", []),
            today=TODAY,
            generated_at=datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc),
        )

    def codes(result) -> set:
        return {f["code"] for f in result["findings"]}

    def quality_codes(result) -> set:
        return {f["code"] for f in result["data_quality"]["findings"]}

    def signal_codes(result) -> set:
        return {s["code"] for s in result["positive_signals"]}

    def quality_evidence(result, code) -> dict:
        return next(f["evidence"] for f in result["data_quality"]["findings"] if f["code"] == code)

    def severity_of(result, code) -> str:
        return next(f["severity"] for f in result["findings"] if f["code"] == code)

    def obs(days_ago, weight=None, temp=None, id=1):
        return HealthObservation(id=id, dog_id=1, observation_date=ago(days_ago),
                                 weight_kg=weight, temperature_c=temp)

    def vax(name="DHPP", administered=None, due=None, status="completed", id=1):
        return Vaccination(id=id, dog_id=1, vaccine_name=name, status=status,
                           administered_date=administered, next_due_date=due)

    def med(name="Drug", start=None, end=None, status="active", id=1):
        return Medication(id=id, dog_id=1, medication_name=name, dosage="1 tablet",
                          frequency="daily", start_date=start or ago(10),
                          end_date=end, status=status)

    def fup(reason="Recheck", due=None, completed=None, status="pending", id=1):
        return FollowUp(id=id, dog_id=1, reason=reason, due_date=due or ahead(30),
                        completed_date=completed, status=status)

    def rec(title="Visit", kind="checkup", when=None, id=1):
        return MedicalRecord(id=id, dog_id=1, record_type=kind, title=title,
                             visit_date=when or ago(5))

    # ---------------------------------------------------------- vaccinations
    section("1. Vaccination rules")
    r = analyse(vaccinations=[vax(administered=ago(300), due=ahead(65))])
    check("up to date -> no finding, positive signal", not codes(r) and "vaccination.up_to_date" in signal_codes(r), codes(r))
    r = analyse(vaccinations=[vax(administered=ago(340), due=ahead(20))])
    check("due within 30 days -> due_soon (low)", codes(r) == {"vaccination.due_soon"} and severity_of(r, "vaccination.due_soon") == "low")
    check("due_soon evidence states days until due",
          r["findings"][0]["evidence"]["days_until_due"] == 20)
    r = analyse(vaccinations=[vax(administered=ago(400), due=ago(10))])
    check("overdue by 10 days -> moderate", severity_of(r, "vaccination.overdue") == "moderate")
    check("overdue evidence states days overdue", r["findings"][0]["evidence"]["days_overdue"] == 10)
    r = analyse(vaccinations=[vax(administered=ago(500), due=ago(90))])
    check("overdue beyond 60 days -> high", severity_of(r, "vaccination.overdue") == "high")

    # The stored status must not decide the outcome (§3).
    r = analyse(vaccinations=[vax(administered=ago(400), due=ago(30), status="completed")])
    check("stored status 'completed' does not hide a passed due date",
          "vaccination.overdue" in codes(r))
    r = analyse(vaccinations=[vax(administered=ago(10), due=ahead(355), status="overdue")])
    check("stored status 'overdue' does not create a finding when dates disagree",
          not codes(r), codes(r))
    check("stored status is still reported as evidence",
          analyse(vaccinations=[vax(administered=ago(400), due=ago(30))])["findings"][0]["evidence"]["stored_status"] == "completed")

    r = analyse(vaccinations=[vax(due=None, status="completed")])
    check("missing due date -> data quality, not a health finding",
          "vaccination.missing_due_date" in quality_codes(r) and not codes(r))
    r = analyse(vaccinations=[vax(administered=ago(10), due=ago(40))])
    check("due date before administered date -> data quality",
          "vaccination.inconsistent_dates" in quality_codes(r))
    r = analyse(vaccinations=[vax(administered=ahead(5), due=ahead(400))])
    check("administered date in the future -> data quality",
          "vaccination.future_administered_date" in quality_codes(r))
    r = analyse()
    check("no vaccinations at all -> data quality", "vaccination.none_recorded" in quality_codes(r))

    # ----------------------------------------------------------- medications
    section("2. Medication rules")
    r = analyse(medications=[med(start=ago(10))])
    check("recent active course -> no finding", not codes(r))
    r = analyse(medications=[med(start=ago(200), end=ago(5), status="active")])
    check("active past its end date -> moderate", severity_of(r, "medication.active_past_end_date") == "moderate")
    check("evidence gives days past end", r["findings"][0]["evidence"]["days_past_end"] == 5)
    r = analyse(medications=[med(start=ago(200))])
    check("active over 180 days with no end date -> low", severity_of(r, "medication.long_active_no_end_date") == "low")
    r = analyse(medications=[med(start=ago(100), end=ago(90), status="completed")])
    check("completed course -> positive signal, no finding",
          not codes(r) and "medication.course_completed" in signal_codes(r))
    r = analyse(medications=[med(status="completed", end=None)])
    check("completed with no end date -> data quality", "medication.missing_end_date" in quality_codes(r))
    r = analyse(medications=[med(start=ago(10), end=ago(30), status="discontinued")])
    check("end before start -> data quality", "medication.inconsistent_dates" in quality_codes(r))
    r = analyse(medications=[med(name=f"D{i}", id=i, start=ago(5)) for i in range(1, 4)])
    check("three active at once -> low finding", severity_of(r, "medication.many_active") == "low")
    check("many_active evidence lists them", len(r["findings"][0]["evidence"]["medications"]) == 3)
    r = analyse(medications=[med(name=f"D{i}", id=i, start=ago(5)) for i in range(1, 3)])
    check("two active -> no finding", "medication.many_active" not in codes(r))

    # ------------------------------------------------------------ follow-ups
    section("3. Follow-up rules")
    r = analyse(follow_ups=[fup(due=ahead(30))])
    check("pending, far off -> no finding, positive signal",
          not codes(r) and "follow_up.none_overdue" in signal_codes(r))
    r = analyse(follow_ups=[fup(due=ahead(5))])
    check("due within 7 days -> low", severity_of(r, "follow_up.due_soon") == "low")
    r = analyse(follow_ups=[fup(due=ago(5))])
    check("overdue by 5 days -> moderate", severity_of(r, "follow_up.overdue") == "moderate")
    r = analyse(follow_ups=[fup(due=ago(30))])
    check("overdue beyond 14 days -> high", severity_of(r, "follow_up.overdue") == "high")
    check("overdue evidence states days overdue", r["findings"][0]["evidence"]["days_overdue"] == 30)
    r = analyse(follow_ups=[fup(due=ago(20), status="missed")])
    check("missed -> high", severity_of(r, "follow_up.missed") == "high")
    r = analyse(follow_ups=[fup(due=ago(20), completed=ago(19), status="completed")])
    check("completed -> no finding", not codes(r))
    r = analyse(follow_ups=[fup(status="completed", completed=None)])
    check("completed with no date -> data quality", "follow_up.missing_completed_date" in quality_codes(r))
    r = analyse(follow_ups=[fup(status="cancelled", completed=ago(3))])
    check("completion date on a cancelled follow-up -> data quality",
          "follow_up.completion_status_mismatch" in quality_codes(r))

    # ---------------------------------------------------------------- weight
    section("4. Weight trend rules")
    r = analyse(observations=[obs(60, weight=20.0, id=1), obs(5, weight=19.8, id=2)])
    check("stable -> no finding, positive signal",
          not codes(r) and "weight.stable" in signal_codes(r))
    series = r["data_quality"]["weight_series"]
    check("series reports first, latest, change, count and period",
          series["first_weight_kg"] == 20.0 and series["latest_weight_kg"] == 19.8
          and series["absolute_change_kg"] == -0.2 and series["percent_change"] == -1.0
          and series["observation_count"] == 2 and series["period_days"] == 55, series)

    r = analyse(observations=[obs(60, weight=20.0, id=1), obs(5, weight=18.6, id=2)])
    check("7% decline -> moderate", severity_of(r, "weight.decline") == "moderate")
    r = analyse(observations=[obs(90, weight=18.2, id=1), obs(69, weight=16.7, id=2)])
    check("8.2% decline -> moderate", severity_of(r, "weight.decline") == "moderate")
    r = analyse(observations=[obs(60, weight=20.0, id=1), obs(5, weight=17.5, id=2)])
    check("12.5% decline -> high", severity_of(r, "weight.significant_decline") == "high")
    check("evidence quotes both weights and the period",
          r["findings"][0]["evidence"]["first_weight_kg"] == 20.0
          and r["findings"][0]["evidence"]["latest_weight_kg"] == 17.5
          and r["findings"][0]["evidence"]["period_days"] == 55)
    r = analyse(observations=[obs(20, weight=20.0, id=1), obs(10, weight=18.8, id=2)])
    check("6% drop within 14 days -> rapid change (high)", severity_of(r, "weight.rapid_change") == "high")
    r = analyse(observations=[obs(60, weight=20.0, id=1), obs(40, weight=19.7, id=2),
                              obs(20, weight=19.4, id=3), obs(5, weight=19.2, id=4)])
    check("three consecutive falls -> repeated decline (moderate)",
          severity_of(r, "weight.repeated_decline") == "moderate")
    check("small consecutive falls do not trigger the total-decline rule",
          "weight.decline" not in codes(r) and "weight.significant_decline" not in codes(r))

    r = analyse(observations=[obs(5, weight=20.0)])
    check("single observation -> no trend finding, data quality instead",
          not codes(r) and "weight.insufficient_data" in quality_codes(r))
    check("insufficient-data evidence states the count",
          quality_evidence(r, "weight.insufficient_data")["observation_count"] == 1)
    r = analyse(observations=[obs(300, weight=30.0, id=1), obs(5, weight=20.0, id=2)])
    check("observation outside the 180-day window is not trended",
          "weight.significant_decline" not in codes(r)
          and "weight.insufficient_data" in quality_codes(r))
    r = analyse(observations=[obs(60, weight=18.0, id=1), obs(5, weight=20.0, id=2)])
    check("weight gain -> no decline finding", not codes(r), codes(r))

    # ----------------------------------------------------------- temperature
    section("5. Temperature rules")
    r = analyse(observations=[obs(30, temp=38.5, id=1), obs(5, temp=38.7, id=2)])
    check("within monitoring range -> no finding, positive signal",
          not codes(r) and "temperature.within_range" in signal_codes(r))
    r = analyse(observations=[obs(5, temp=39.8, id=1), obs(40, temp=38.5, id=2)])
    check("latest above threshold -> moderate", severity_of(r, "temperature.high") == "moderate")
    check("evidence names the threshold, not a diagnosis",
          r["findings"][0]["evidence"]["threshold_c"] == hi.TEMPERATURE_HIGH_C
          and "diagnosis" in r["findings"][0]["evidence"]["note"])
    r = analyse(observations=[obs(5, temp=41.0)])
    check("latest far above threshold -> high", severity_of(r, "temperature.high") == "high")
    r = analyse(observations=[obs(5, temp=37.0)])
    check("latest below threshold -> moderate", severity_of(r, "temperature.low") == "moderate")
    r = analyse(observations=[obs(5, temp=36.2)])
    check("latest far below threshold -> high", severity_of(r, "temperature.low") == "high")
    r = analyse(observations=[obs(30, temp=39.6, id=1), obs(5, temp=39.9, id=2)])
    check("two abnormal readings -> repeated_abnormal (high)",
          severity_of(r, "temperature.repeated_abnormal") == "high")
    r = analyse(observations=[obs(12, temp=38.2, id=1), obs(5, temp=39.9, id=2)])
    check("1.7 C jump within 14 days -> sudden change", "temperature.sudden_change" in codes(r))
    r = analyse(observations=[obs(5, temp=38.5)])
    check("one reading -> data quality, no repeated/sudden finding",
          not codes(r) and "temperature.insufficient_data" in quality_codes(r))
    r = analyse(observations=[obs(5, weight=20.0)])
    check("no temperature at all -> data quality", "temperature.none_recorded" in quality_codes(r))
    r = analyse(observations=[obs(5, temp=34.0)])
    check("34 C is valid input but outside the monitoring range -> flagged",
          "temperature.low" in codes(r))
    check("monitoring thresholds differ from the 30-45 input range",
          (hi.TEMPERATURE_LOW_C, hi.TEMPERATURE_HIGH_C) != (30.0, 45.0))

    # -------------------------------------------------------- medical records
    section("6. Medical record rules")
    r = analyse(records=[rec(when=ago(5))])
    check("recent visit with no follow-up -> low",
          severity_of(r, "medical_record.recent_visit_no_follow_up") == "low")
    check("recent visit is also a positive signal", "medical_record.recent_visit" in signal_codes(r))
    r = analyse(records=[rec(when=ago(5))], follow_ups=[fup(due=ahead(20))])
    check("recent visit with a follow-up -> no finding",
          "medical_record.recent_visit_no_follow_up" not in codes(r))
    r = analyse(records=[rec(kind="surgery", when=ago(40))])
    check("surgery with no follow-up -> moderate",
          severity_of(r, "medical_record.no_follow_up_after_treatment") == "moderate")
    r = analyse(records=[rec(kind="checkup", when=ago(40))])
    check("routine checkup does not imply a follow-up",
          "medical_record.no_follow_up_after_treatment" not in codes(r))
    r = analyse(records=[rec(id=i, when=ago(i * 5)) for i in range(1, 4)])
    check("three visits in 30 days -> moderate",
          severity_of(r, "medical_record.repeated_visits") == "moderate")
    r = analyse()
    check("no records -> data quality", "medical_record.none_recorded" in quality_codes(r))

    # --------------------------------------------------------- data quality
    section("7. Data quality is separate from health")
    r = analyse()
    check("a dog with no data at all scores 0 risk", r["risk_score"] == 0 and r["risk_level"] == "low")
    check("...but its data quality score is reduced", r["data_quality"]["score"] < 100)
    check("...and every gap is listed as a data-quality finding",
          {"vaccination.none_recorded", "observation.none_recorded",
           "medical_record.none_recorded"} <= quality_codes(r))
    check("no data-quality finding carries severity points",
          all("points" not in f for f in r["data_quality"]["findings"]))
    r = analyse(observations=[obs(200, weight=20.0)])
    check("stale observations -> data quality", "observation.stale" in quality_codes(r))
    check("data quality reports counts and both series",
          {"counts", "weight_series", "temperature_series", "days_since_last_observation"}
          <= set(r["data_quality"]))

    # --------------------------------------------------------------- scoring
    section("8. Risk scoring")
    r = analyse()
    check("nothing found -> score 0, level low", (r["risk_score"], r["risk_level"]) == (0, "low"))
    r = analyse(follow_ups=[fup(due=ahead(5))])
    check("one low finding -> 5, low", (r["risk_score"], r["risk_level"]) == (5, "low"))
    r = analyse(follow_ups=[fup(due=ago(5))])
    check("one moderate finding -> 10, moderate", (r["risk_score"], r["risk_level"]) == (10, "moderate"))
    r = analyse(follow_ups=[fup(due=ago(30))])
    check("one high finding -> 20, high", (r["risk_score"], r["risk_level"]) == (20, "high"))
    r = analyse(follow_ups=[fup(id=1, due=ago(30)), fup(id=2, due=ago(40), status="missed")],
                observations=[obs(60, weight=20.0, id=1), obs(5, weight=17.0, id=2)])
    check("three high findings -> 60, critical", r["risk_score"] >= 60 and r["risk_level"] == "critical")
    check("score is the sum of the findings' points",
          r["risk_score"] == min(100, sum(f["points"] for f in r["findings"])))
    check("breakdown lists every finding's contribution",
          len(r["score_breakdown"]["points_by_finding"]) == len(r["findings"]))
    check("finding counts match the findings list",
          r["finding_counts"]["total"] == len(r["findings"]))

    many = [fup(id=i, due=ago(30 + i), status="missed") for i in range(1, 12)]
    r = analyse(follow_ups=many)
    check("score is capped at 100", r["risk_score"] == 100 and r["score_breakdown"]["total_before_cap"] > 100)
    check("findings are ordered most severe first",
          [f["severity"] for f in r["findings"]] == sorted(
              [f["severity"] for f in r["findings"]],
              key=lambda s: -hi.SEVERITY_ORDER.index(s)))

    # Deterministic: same input, same output, every time.
    args = dict(follow_ups=[fup(due=ago(9))],
                observations=[obs(40, weight=20.0, id=1), obs(3, weight=18.0, id=2)],
                vaccinations=[vax(administered=ago(400), due=ago(20))])
    first, second = analyse(**args), analyse(**args)
    check("identical input produces identical output", first == second)
    check("nothing in the result is random", first["risk_score"] == analyse(**args)["risk_score"])

    check("every finding carries the required fields", all(
        {"category", "severity", "title", "reason", "evidence", "recommendation"} <= set(f)
        and f["evidence"] and f["reason"]
        for f in first["findings"]), first["findings"][0] if first["findings"] else "")
    check("result has the documented top-level shape",
          {"dog_id", "risk_level", "risk_score", "findings", "positive_signals",
           "data_quality", "generated_at"} <= set(first))
    check("every severity used is a known one",
          {f["severity"] for f in first["findings"]} <= set(hi.SEVERITY_POINTS))

    # Wording: patterns, never diagnoses.
    text = " ".join(f"{f['title']} {f['reason']} {f['recommendation']}" for f in first["findings"]).lower()
    check("no diagnostic language in the findings",
          not any(w in text for w in ("diagnos", "disease", "unhealthy", "is ill", "suffers")), text[:200])
    check("result states the method and is not called ML",
          "no machine learning" in first["method"] and "machine learning" not in first["disclaimer"].lower())

    # ------------------------------------------------------------ summarise
    section("9. Summary view")
    s = hi.summarise(first)
    check("summary carries level, score and counts",
          (s["risk_level"], s["risk_score"]) == (first["risk_level"], first["risk_score"])
          and s["finding_counts"] == first["finding_counts"])
    check("summary holds at most three findings", len(s["top_findings"]) <= 3)
    check("summary drops the heavy payload", "config" not in s and "evidence" not in str(s.keys()))

    # ------------------------------------------------------------------ API
    section("10. API endpoint")
    import app as app_module

    import medical_demo_data

    app = app_module.app
    client = app.test_client()
    with app.app_context():
        medical_demo_data.load(TODAY)

    def login(email, password):
        r = client.post("/api/auth/login", json={"email": email, "password": password})
        return {"Authorization": f"Bearer {r.json['token']}"}

    admin, user = login("admin@dogo-paw.org", "admin123"), login("demo@dogo-paw.org", "demo123")
    url = "/api/dogs/4/medical/health-analysis"
    check("anonymous -> 401", client.get(url).status_code == 401)
    check("anonymous summary -> 401", client.get(url + "/summary").status_code == 401)
    check("signed-in user -> 200", client.get(url, headers=user).status_code == 200)
    check("admin -> 200", client.get(url, headers=admin).status_code == 200)
    check("unknown dog -> 404",
          client.get("/api/dogs/9999/medical/health-analysis", headers=admin).status_code == 404)
    check("unknown dog, summary -> 404",
          client.get("/api/dogs/9999/medical/health-analysis/summary", headers=admin).status_code == 404)

    body = client.get(url, headers=admin).get_json()
    check("endpoint returns the analysis for that dog", body["dog_id"] == 4)
    check("endpoint reports the thresholds it applied", "config" in body)
    check("two calls agree except for the timestamp", {
        k: v for k, v in client.get(url, headers=admin).get_json().items() if k != "generated_at"
    } == {k: v for k, v in body.items() if k != "generated_at"})
    summary_body = client.get(url + "/summary", headers=admin).get_json()
    check("summary endpoint agrees with the full analysis",
          summary_body["risk_score"] == body["risk_score"]
          and summary_body["risk_level"] == body["risk_level"])
    check("a dog with no medical data still analyses",
          client.get("/api/dogs/2/medical/health-analysis", headers=admin).get_json()["risk_score"] == 0)

    # "health-analysis" must not be read as a record type by the list route.
    check("record-type routes still work", client.get(
        "/api/dogs/4/medical/medications", headers=user).get_json()["count"] == 1)
    check("unknown record type still 404s",
          client.get("/api/dogs/4/medical/allergies", headers=user).status_code == 404)
    check("the medical summary endpoint is unchanged",
          set(client.get("/api/dogs/4/medical", headers=user).get_json()) == {
              "dog", "vaccinations", "medications", "recent_observations",
              "follow_ups", "recent_medical_records", "counts"})
    check("public dog endpoints unchanged",
          client.get("/api/dogs").get_json()["count"] == 18
          and "risk_score" not in client.get("/api/dogs/4").get_json()["dog"])

    section("11. Demo fixture produces meaningful results")
    seen = {}
    for dog_id in (1, 4, 8, 13, 15):
        seen[dog_id] = client.get(
            f"/api/dogs/{dog_id}/medical/health-analysis/summary", headers=admin).get_json()
    check("the fixture dog with missed follow-up and weight loss scores highest",
          max(seen, key=lambda d: seen[d]["risk_score"]) == 4, {d: s["risk_score"] for d, s in seen.items()})
    check("every fixture dog produces a valid level",
          all(s["risk_level"] in ("low", "moderate", "high", "critical") for s in seen.values()))
    check("the overdue vaccination on Nala is detected", "vaccination.overdue" in {
        f["code"] for f in client.get(
            "/api/dogs/13/medical/health-analysis", headers=admin).get_json()["findings"]})


def main() -> int:
    if "--child" in sys.argv:
        run_checks()
        print(f"\n{'all passed' if not FAILURES else f'{len(FAILURES)} FAILED: {FAILURES}'}")
        return 1 if FAILURES else 0

    with tempfile.TemporaryDirectory() as tmp:
        return subprocess.run(
            [sys.executable, __file__, "--child"], cwd=HERE,
            env={**os.environ, "DATABASE_URL": f"sqlite:///{Path(tmp) / 'hi.db'}",
                 "APP_ENV": "development", "RATE_LIMIT_ENABLED": "false",
                 "PYTHONIOENCODING": "utf-8"},
            timeout=300,
        ).returncode


if __name__ == "__main__":
    sys.exit(main())
