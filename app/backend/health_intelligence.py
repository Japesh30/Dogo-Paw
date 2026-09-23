"""Health intelligence: deterministic, explainable checks over medical data.

This is a rule engine, not a model. It reads the records stored in Phase 3,
applies the named rules below, and returns findings with the evidence that
produced them. The same records and the same date always produce the same
result; nothing here is trained, fitted, sampled or random.

What it does NOT do:

* diagnose. It reports patterns in the data ("a follow-up appears overdue"),
  never a condition, and never that a dog is healthy or ill.
* judge treatment. It never comments on whether a medication is right, safe or
  interacts with another; only on whether its dates and status are consistent.
* invent requirements. Every rule reads fields that are actually recorded.

Three kinds of output, kept apart on purpose:

* `findings` — patterns in medical data that may need attention. These score.
* `data_quality.findings` — records that are missing or internally
  inconsistent. Missing data is not bad health, so these never score.
* `ml_anomalies` — the machine-learning layer's separate view of the
  observation history (ml/health_anomaly_service.py). It is reported beside
  the rules, never merged into them, and **never changes `risk_score`**: the
  score stays a function of these rules alone, so it means today what it meant
  before the model existed.

Thresholds are all constants in the CONFIG block. `config()` returns them so
the API can show the caller exactly what was applied.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from models import HealthObservation, MedicalRecord, Medication, Vaccination

# --------------------------------------------------------------------------- #
# CONFIG — every threshold the engine applies. Nothing below hardcodes a number
# that belongs here.
# --------------------------------------------------------------------------- #

# --- vaccinations ---
VACCINATION_DUE_SOON_DAYS = 30      # due within this window -> "due soon"
VACCINATION_OVERDUE_HIGH_DAYS = 60  # overdue by more than this -> high severity

# --- follow-ups ---
FOLLOW_UP_DUE_SOON_DAYS = 7
FOLLOW_UP_OVERDUE_HIGH_DAYS = 14

# --- medications ---
# An active course running this long with no end date recorded is a status
# worth revisiting; it is not a statement about the medication itself.
MEDICATION_LONG_ACTIVE_DAYS = 180
MEDICATION_MANY_ACTIVE = 3          # this many or more active at once -> note it

# --- weight ---
WEIGHT_WINDOW_DAYS = 180            # only observations this recent are trended
WEIGHT_MIN_OBSERVATIONS = 2         # fewer than this: no trend, ever
WEIGHT_STABLE_PCT = 3.0             # within +/- this over the window -> positive signal
WEIGHT_DECLINE_PCT = 5.0            # total loss over the window -> moderate
WEIGHT_SIGNIFICANT_DECLINE_PCT = 10.0  # total loss over the window -> high
WEIGHT_RAPID_DECLINE_PCT = 5.0      # loss between two readings...
WEIGHT_RAPID_DECLINE_DAYS = 14      # ...no more than this far apart -> high
WEIGHT_REPEATED_DECLINE_COUNT = 3   # consecutive falling readings -> moderate

# --- temperature ---
# Monitoring thresholds, deliberately NOT the 30-45 C plausibility range that
# medical.py validates against on input. A reading outside these is flagged for
# a human to look at; it is not a diagnosis of fever or hypothermia.
TEMPERATURE_HIGH_C = 39.4
TEMPERATURE_LOW_C = 37.2
TEMPERATURE_VERY_HIGH_C = 40.5      # outside these -> high rather than moderate
TEMPERATURE_VERY_LOW_C = 36.5
TEMPERATURE_WINDOW_DAYS = 60        # readings this recent are considered
TEMPERATURE_REPEATED_COUNT = 2      # this many abnormal in the window -> escalate
TEMPERATURE_SUDDEN_CHANGE_C = 1.5   # change between consecutive readings...
TEMPERATURE_SUDDEN_CHANGE_DAYS = 14  # ...no more than this far apart

# --- medical records ---
RECORD_RECENT_DAYS = 30             # a visit this recent counts as recent
RECORD_REPEATED_COUNT = 3           # this many visits...
RECORD_REPEATED_WINDOW_DAYS = 30    # ...within this window -> note it
# Visit types where the records themselves imply aftercare. Kept small and
# explicit: the engine never guesses that some other visit needed a follow-up.
RECORD_FOLLOW_UP_EXPECTED_TYPES = frozenset({"surgery", "emergency", "treatment"})
RECORD_FOLLOW_UP_EXPECTED_DAYS = 90

# --- data quality ---
OBSERVATION_STALE_DAYS = 90         # nothing observed in this long -> flag the gap

# --- scoring ---
SEVERITY_POINTS = {"critical": 30, "high": 20, "moderate": 10, "low": 5}
SEVERITY_ORDER = ["low", "moderate", "high", "critical"]
MAX_RISK_SCORE = 100
# Score bands. A band's name applies from its lower bound up to the next one.
RISK_BANDS = [(0, "low"), (15, "moderate"), (35, "high"), (60, "critical")]
# The level is never lower than the worst single finding: one critical finding
# scores 30, which by band alone would read "moderate", and that would
# understate it.
SEVERITY_TO_LEVEL = {"low": "low", "moderate": "moderate", "high": "high", "critical": "critical"}

# Each missing piece of context costs the data-quality score this much.
DATA_QUALITY_PENALTY = 15


def config() -> dict:
    """Every threshold applied, so a caller can see what produced a result."""
    return {
        "vaccination": {
            "due_soon_days": VACCINATION_DUE_SOON_DAYS,
            "overdue_high_days": VACCINATION_OVERDUE_HIGH_DAYS,
        },
        "follow_up": {
            "due_soon_days": FOLLOW_UP_DUE_SOON_DAYS,
            "overdue_high_days": FOLLOW_UP_OVERDUE_HIGH_DAYS,
        },
        "medication": {
            "long_active_days": MEDICATION_LONG_ACTIVE_DAYS,
            "many_active": MEDICATION_MANY_ACTIVE,
        },
        "weight": {
            "window_days": WEIGHT_WINDOW_DAYS,
            "min_observations": WEIGHT_MIN_OBSERVATIONS,
            "stable_pct": WEIGHT_STABLE_PCT,
            "decline_pct": WEIGHT_DECLINE_PCT,
            "significant_decline_pct": WEIGHT_SIGNIFICANT_DECLINE_PCT,
            "rapid_decline_pct": WEIGHT_RAPID_DECLINE_PCT,
            "rapid_decline_days": WEIGHT_RAPID_DECLINE_DAYS,
            "repeated_decline_count": WEIGHT_REPEATED_DECLINE_COUNT,
        },
        "temperature": {
            "high_c": TEMPERATURE_HIGH_C,
            "low_c": TEMPERATURE_LOW_C,
            "very_high_c": TEMPERATURE_VERY_HIGH_C,
            "very_low_c": TEMPERATURE_VERY_LOW_C,
            "window_days": TEMPERATURE_WINDOW_DAYS,
            "repeated_count": TEMPERATURE_REPEATED_COUNT,
            "sudden_change_c": TEMPERATURE_SUDDEN_CHANGE_C,
            "sudden_change_days": TEMPERATURE_SUDDEN_CHANGE_DAYS,
            "note": (
                "Monitoring thresholds for flagging readings to a human. Not a "
                "clinical range, and not the 30-45 C input plausibility check."
            ),
        },
        "medical_record": {
            "recent_days": RECORD_RECENT_DAYS,
            "repeated_count": RECORD_REPEATED_COUNT,
            "repeated_window_days": RECORD_REPEATED_WINDOW_DAYS,
            "follow_up_expected_types": sorted(RECORD_FOLLOW_UP_EXPECTED_TYPES),
            "follow_up_expected_days": RECORD_FOLLOW_UP_EXPECTED_DAYS,
        },
        "data_quality": {"observation_stale_days": OBSERVATION_STALE_DAYS},
        "scoring": {
            "severity_points": dict(SEVERITY_POINTS),
            "max_risk_score": MAX_RISK_SCORE,
            "risk_bands": [{"from_score": s, "level": n} for s, n in RISK_BANDS],
            "level_is_at_least_worst_finding": True,
        },
    }


# --------------------------------------------------------------------------- #
# Builders
# --------------------------------------------------------------------------- #
def finding(code, category, severity, title, reason, evidence, recommendation) -> dict:
    """One pattern worth a human's attention.

    `reason` says what the data shows; `evidence` carries the numbers and dates
    behind it so nothing has to be taken on trust; `recommendation` is an
    administrative next step, never treatment advice.
    """
    return {
        "code": code,
        "category": category,
        "severity": severity,
        "title": title,
        "reason": reason,
        "evidence": evidence,
        "recommendation": recommendation,
        "points": SEVERITY_POINTS[severity],
    }


def quality_finding(code, category, title, reason, evidence, recommendation) -> dict:
    """A gap or inconsistency in the records. Never scored as health risk."""
    return {
        "code": code,
        "category": category,
        "severity": "info",
        "title": title,
        "reason": reason,
        "evidence": evidence,
        "recommendation": recommendation,
    }


def signal(code, category, title, detail, evidence=None) -> dict:
    """A positive observation about the data. Not a statement of health."""
    return {
        "code": code,
        "category": category,
        "title": title,
        "detail": detail,
        "evidence": evidence or {},
    }


def _days(later: date, earlier: date) -> int:
    return (later - earlier).days


def _pct(first: float, last: float) -> float:
    return round((last - first) / first * 100, 1) if first else 0.0


# --------------------------------------------------------------------------- #
# Rules, one function per category. Each returns
# (findings, quality_findings, signals).
# --------------------------------------------------------------------------- #
def check_vaccinations(rows: list[Vaccination], today: date):
    findings, quality, signals = [], [], []

    if not rows:
        quality.append(quality_finding(
            "vaccination.none_recorded", "vaccination", "No vaccination records",
            "No vaccination has been recorded for this dog.",
            {"vaccination_count": 0},
            "Add the vaccination history, or record that none is known.",
        ))
        return findings, quality, signals

    overdue, due_soon = [], []
    for row in rows:
        label = row.vaccine_name

        # Inconsistent dates are a records problem, not a health pattern.
        if row.administered_date and row.next_due_date and row.next_due_date < row.administered_date:
            quality.append(quality_finding(
                "vaccination.inconsistent_dates", "vaccination", "Vaccination dates disagree",
                f"{label}: the next due date is earlier than the date it was given.",
                {"vaccination_id": row.id, "vaccine_name": label,
                 "administered_date": row.administered_date.isoformat(),
                 "next_due_date": row.next_due_date.isoformat()},
                "Correct the dates on this vaccination record.",
            ))
        if row.administered_date and row.administered_date > today:
            quality.append(quality_finding(
                "vaccination.future_administered_date", "vaccination",
                "Vaccination dated in the future",
                f"{label} is recorded as given on a future date.",
                {"vaccination_id": row.id, "administered_date": row.administered_date.isoformat(),
                 "today": today.isoformat()},
                "Correct the administered date.",
            ))

        if row.next_due_date is None:
            # Stored status is not trusted; without a due date nothing can be
            # worked out either way, so this is a data gap.
            quality.append(quality_finding(
                "vaccination.missing_due_date", "vaccination", "No next due date recorded",
                f"{label} has no next due date, so its schedule cannot be checked.",
                {"vaccination_id": row.id, "vaccine_name": label, "stored_status": row.status},
                "Record the next due date for this vaccine.",
            ))
            continue

        # Calculated from the dates, never read from row.status (§3).
        days = _days(today, row.next_due_date)
        if days > 0:
            overdue.append((row, days))
        elif -days <= VACCINATION_DUE_SOON_DAYS:
            due_soon.append((row, -days))

    for row, days in overdue:
        severity = "high" if days > VACCINATION_OVERDUE_HIGH_DAYS else "moderate"
        findings.append(finding(
            "vaccination.overdue", "vaccination", severity,
            f"Vaccination appears overdue: {row.vaccine_name}",
            f"{row.vaccine_name} was due on {row.next_due_date.isoformat()}, {days} days ago.",
            {"vaccination_id": row.id, "vaccine_name": row.vaccine_name,
             "next_due_date": row.next_due_date.isoformat(), "days_overdue": days,
             "stored_status": row.status, "today": today.isoformat(),
             "high_severity_after_days": VACCINATION_OVERDUE_HIGH_DAYS},
            "Check with the vet whether this vaccination is still outstanding.",
        ))

    for row, days in due_soon:
        findings.append(finding(
            "vaccination.due_soon", "vaccination", "low",
            f"Vaccination due soon: {row.vaccine_name}",
            f"{row.vaccine_name} is due on {row.next_due_date.isoformat()}, in {days} days.",
            {"vaccination_id": row.id, "vaccine_name": row.vaccine_name,
             "next_due_date": row.next_due_date.isoformat(), "days_until_due": days,
             "due_soon_window_days": VACCINATION_DUE_SOON_DAYS},
            "Book the appointment.",
        ))

    scheduled = [r for r in rows if r.next_due_date]
    if scheduled and not overdue and not due_soon:
        nearest = min(r.next_due_date for r in scheduled)
        signals.append(signal(
            "vaccination.up_to_date", "vaccination", "Vaccinations up to date",
            f"No vaccination is overdue or due within {VACCINATION_DUE_SOON_DAYS} days.",
            {"vaccination_count": len(rows), "next_due_date": nearest.isoformat()},
        ))
    return findings, quality, signals


def check_medications(rows: list[Medication], today: date):
    findings, quality, signals = [], [], []

    active = [r for r in rows if r.status == "active"]

    for row in rows:
        label = row.medication_name
        if row.end_date and row.end_date < row.start_date:
            quality.append(quality_finding(
                "medication.inconsistent_dates", "medication", "Medication dates disagree",
                f"{label}: the end date is earlier than the start date.",
                {"medication_id": row.id, "medication_name": label,
                 "start_date": row.start_date.isoformat(), "end_date": row.end_date.isoformat()},
                "Correct the dates on this medication record.",
            ))
        if row.status in {"completed", "discontinued"} and row.end_date is None:
            quality.append(quality_finding(
                "medication.missing_end_date", "medication", "No end date on a finished course",
                f"{label} is marked {row.status} but has no end date.",
                {"medication_id": row.id, "medication_name": label, "status": row.status},
                "Record when the course ended.",
            ))

        if row.status == "active" and row.end_date and row.end_date < today:
            findings.append(finding(
                "medication.active_past_end_date", "medication", "moderate",
                f"Medication still marked active past its end date: {label}",
                f"{label} ended on {row.end_date.isoformat()} "
                f"({_days(today, row.end_date)} days ago) but is still recorded as active.",
                {"medication_id": row.id, "medication_name": label,
                 "end_date": row.end_date.isoformat(), "days_past_end": _days(today, row.end_date),
                 "status": row.status},
                "Confirm whether the course finished and update its status.",
            ))
        if row.status == "active" and row.end_date is None:
            running = _days(today, row.start_date)
            if running > MEDICATION_LONG_ACTIVE_DAYS:
                findings.append(finding(
                    "medication.long_active_no_end_date", "medication", "low",
                    f"Long-running medication with no end date: {label}",
                    f"{label} has been active for {running} days with no end date recorded.",
                    {"medication_id": row.id, "medication_name": label,
                     "start_date": row.start_date.isoformat(), "days_active": running,
                     "threshold_days": MEDICATION_LONG_ACTIVE_DAYS},
                    "Confirm the course is still intended, and record an end date or review date.",
                ))

    if len(active) >= MEDICATION_MANY_ACTIVE:
        findings.append(finding(
            "medication.many_active", "medication", "low",
            f"{len(active)} medications recorded as active",
            f"{len(active)} medications are currently marked active. This counts records "
            "only; it is not an assessment of the medications themselves.",
            {"active_count": len(active), "threshold": MEDICATION_MANY_ACTIVE,
             "medications": [r.medication_name for r in active]},
            "Confirm the list is current and that finished courses have been closed off.",
        ))

    completed = [r for r in rows if r.status == "completed" and r.end_date]
    if completed:
        latest = max(completed, key=lambda r: r.end_date)
        signals.append(signal(
            "medication.course_completed", "medication", "Medication course completed",
            f"{latest.medication_name} was recorded as completed on {latest.end_date.isoformat()}.",
            {"completed_count": len(completed)},
        ))
    return findings, quality, signals


def check_follow_ups(rows, today: date):
    findings, quality, signals = [], [], []

    pending = [r for r in rows if r.status == "pending"]
    overdue = [(r, _days(today, r.due_date)) for r in pending if r.due_date < today]
    due_soon = [(r, _days(r.due_date, today)) for r in pending
                if today <= r.due_date <= today + timedelta(days=FOLLOW_UP_DUE_SOON_DAYS)]

    for row, days in overdue:
        severity = "high" if days > FOLLOW_UP_OVERDUE_HIGH_DAYS else "moderate"
        findings.append(finding(
            "follow_up.overdue", "follow_up", severity,
            f"Follow-up appears overdue: {row.reason}",
            f"'{row.reason}' was due on {row.due_date.isoformat()}, {days} days ago, "
            "and is still pending.",
            {"follow_up_id": row.id, "reason": row.reason, "due_date": row.due_date.isoformat(),
             "days_overdue": days, "status": row.status,
             "high_severity_after_days": FOLLOW_UP_OVERDUE_HIGH_DAYS},
            "Arrange the follow-up, or close it off if it already happened.",
        ))

    for row, days in due_soon:
        findings.append(finding(
            "follow_up.due_soon", "follow_up", "low",
            f"Follow-up due soon: {row.reason}",
            f"'{row.reason}' is due on {row.due_date.isoformat()}, in {days} days.",
            {"follow_up_id": row.id, "reason": row.reason, "due_date": row.due_date.isoformat(),
             "days_until_due": days, "due_soon_window_days": FOLLOW_UP_DUE_SOON_DAYS},
            "Confirm the appointment.",
        ))

    for row in [r for r in rows if r.status == "missed"]:
        findings.append(finding(
            "follow_up.missed", "follow_up", "high",
            f"Follow-up recorded as missed: {row.reason}",
            f"'{row.reason}', due {row.due_date.isoformat()}, is recorded as missed.",
            {"follow_up_id": row.id, "reason": row.reason, "due_date": row.due_date.isoformat(),
             "days_since_due": _days(today, row.due_date), "status": row.status},
            "Rebook the missed follow-up.",
        ))

    for row in rows:
        if row.status == "completed" and row.completed_date is None:
            quality.append(quality_finding(
                "follow_up.missing_completed_date", "follow_up", "No completion date",
                f"'{row.reason}' is marked completed but has no completion date.",
                {"follow_up_id": row.id, "reason": row.reason},
                "Record when it was completed.",
            ))
        if row.completed_date and row.status != "completed":
            quality.append(quality_finding(
                "follow_up.completion_status_mismatch", "follow_up",
                "Completion date on a follow-up that is not completed",
                f"'{row.reason}' has a completion date but its status is {row.status}.",
                {"follow_up_id": row.id, "status": row.status,
                 "completed_date": row.completed_date.isoformat()},
                "Correct the status or remove the completion date.",
            ))

    if rows and not overdue and not any(r.status == "missed" for r in rows):
        signals.append(signal(
            "follow_up.none_overdue", "follow_up", "No overdue follow-ups",
            "Every recorded follow-up is either upcoming or completed.",
            {"follow_up_count": len(rows), "pending_count": len(pending)},
        ))
    return findings, quality, signals


def weight_series(rows: list[HealthObservation], today: date) -> dict:
    """The weight numbers, computed once and reported whether or not anything
    is flagged, so the caller always sees what the trend was based on."""
    points = sorted(
        (r for r in rows
         if r.weight_kg is not None
         and _days(today, r.observation_date) <= WEIGHT_WINDOW_DAYS),
        key=lambda r: (r.observation_date, r.id),
    )
    series = {
        "observation_count": len(points),
        "window_days": WEIGHT_WINDOW_DAYS,
        "first_weight_kg": None, "latest_weight_kg": None,
        "absolute_change_kg": None, "percent_change": None,
        "first_date": None, "latest_date": None, "period_days": None,
    }
    if not points:
        return series
    first, last = points[0], points[-1]
    series.update(
        first_weight_kg=first.weight_kg, latest_weight_kg=last.weight_kg,
        first_date=first.observation_date.isoformat(),
        latest_date=last.observation_date.isoformat(),
        absolute_change_kg=round(last.weight_kg - first.weight_kg, 2),
        percent_change=_pct(first.weight_kg, last.weight_kg),
        period_days=_days(last.observation_date, first.observation_date),
    )
    return series


def check_weight(rows: list[HealthObservation], today: date):
    findings, quality, signals = [], [], []
    series = weight_series(rows, today)
    points = sorted(
        (r for r in rows
         if r.weight_kg is not None
         and _days(today, r.observation_date) <= WEIGHT_WINDOW_DAYS),
        key=lambda r: (r.observation_date, r.id),
    )

    # One reading is a fact, not a trend (§6).
    if len(points) < WEIGHT_MIN_OBSERVATIONS:
        quality.append(quality_finding(
            "weight.insufficient_data", "weight", "Not enough weights to show a trend",
            f"{len(points)} weight observation(s) in the last {WEIGHT_WINDOW_DAYS} days; "
            f"at least {WEIGHT_MIN_OBSERVATIONS} are needed before any trend is reported.",
            series,
            "Record weight regularly so changes can be seen.",
        ))
        return findings, quality, signals, series

    pct = series["percent_change"]
    evidence = dict(series)
    change = (f"Weight went from {series['first_weight_kg']} kg on {series['first_date']} "
              f"to {series['latest_weight_kg']} kg on {series['latest_date']}, "
              f"over {series['period_days']} days.")

    if pct <= -WEIGHT_SIGNIFICANT_DECLINE_PCT:
        findings.append(finding(
            "weight.significant_decline", "weight", "high", "Notable weight decrease recorded",
            f"{change} That is a {abs(pct)}% decrease, at or beyond the "
            f"{WEIGHT_SIGNIFICANT_DECLINE_PCT}% threshold.",
            {**evidence, "threshold_pct": -WEIGHT_SIGNIFICANT_DECLINE_PCT},
            "Raise the recorded weight change with the vet.",
        ))
    elif pct <= -WEIGHT_DECLINE_PCT:
        findings.append(finding(
            "weight.decline", "weight", "moderate", "Weight decrease recorded",
            f"{change} That is a {abs(pct)}% decrease, at or beyond the "
            f"{WEIGHT_DECLINE_PCT}% threshold.",
            {**evidence, "threshold_pct": -WEIGHT_DECLINE_PCT},
            "Keep weighing, and mention the change at the next visit.",
        ))

    # A sharp drop between two consecutive readings, which a window total can
    # hide if the weight later recovers.
    for before, after in zip(points, points[1:]):
        gap = _days(after.observation_date, before.observation_date)
        drop = _pct(before.weight_kg, after.weight_kg)
        if gap <= WEIGHT_RAPID_DECLINE_DAYS and drop <= -WEIGHT_RAPID_DECLINE_PCT:
            findings.append(finding(
                "weight.rapid_change", "weight", "high", "Rapid weight change between readings",
                f"Weight went from {before.weight_kg} kg on {before.observation_date.isoformat()} "
                f"to {after.weight_kg} kg on {after.observation_date.isoformat()}: "
                f"{abs(drop)}% in {gap} days.",
                {"from_weight_kg": before.weight_kg, "to_weight_kg": after.weight_kg,
                 "from_date": before.observation_date.isoformat(),
                 "to_date": after.observation_date.isoformat(), "days_between": gap,
                 "percent_change": drop, "threshold_pct": -WEIGHT_RAPID_DECLINE_PCT,
                 "within_days": WEIGHT_RAPID_DECLINE_DAYS},
                "Re-weigh to confirm the reading, and raise it with the vet.",
            ))
            break

    falling = 0
    for before, after in zip(points, points[1:]):
        falling = falling + 1 if after.weight_kg < before.weight_kg else 0
        if falling >= WEIGHT_REPEATED_DECLINE_COUNT - 1:
            recent = points[-WEIGHT_REPEATED_DECLINE_COUNT:]
            findings.append(finding(
                "weight.repeated_decline", "weight", "moderate",
                "Weight fell across consecutive readings",
                f"Weight decreased at {WEIGHT_REPEATED_DECLINE_COUNT} consecutive "
                "observations.",
                {"readings": [{"date": r.observation_date.isoformat(), "weight_kg": r.weight_kg}
                              for r in recent],
                 "consecutive_declines": WEIGHT_REPEATED_DECLINE_COUNT},
                "Keep weighing at regular intervals and share the series with the vet.",
            ))
            break

    if abs(pct) <= WEIGHT_STABLE_PCT:
        signals.append(signal(
            "weight.stable", "weight", "Weight stable across observations",
            f"Weight changed by {pct}% over {series['period_days']} days, within the "
            f"{WEIGHT_STABLE_PCT}% band treated as stable.",
            series,
        ))
    return findings, quality, signals, series


def check_temperature(rows: list[HealthObservation], today: date):
    findings, quality, signals = [], [], []
    points = sorted(
        (r for r in rows
         if r.temperature_c is not None
         and _days(today, r.observation_date) <= TEMPERATURE_WINDOW_DAYS),
        key=lambda r: (r.observation_date, r.id),
    )
    series = {
        "observation_count": len(points),
        "window_days": TEMPERATURE_WINDOW_DAYS,
        "latest_temperature_c": points[-1].temperature_c if points else None,
        "latest_date": points[-1].observation_date.isoformat() if points else None,
        "monitoring_range_c": [TEMPERATURE_LOW_C, TEMPERATURE_HIGH_C],
    }

    if not points:
        quality.append(quality_finding(
            "temperature.none_recorded", "temperature", "No temperature readings",
            f"No temperature has been recorded in the last {TEMPERATURE_WINDOW_DAYS} days.",
            series,
            "Record temperature at routine checks.",
        ))
        return findings, quality, signals, series

    def abnormal(value):
        if value >= TEMPERATURE_HIGH_C:
            return "high"
        return "low" if value <= TEMPERATURE_LOW_C else None

    outside = [r for r in points if abnormal(r.temperature_c)]

    latest = points[-1]
    direction = abnormal(latest.temperature_c)
    if direction:
        extreme = (latest.temperature_c >= TEMPERATURE_VERY_HIGH_C
                   or latest.temperature_c <= TEMPERATURE_VERY_LOW_C)
        threshold = TEMPERATURE_HIGH_C if direction == "high" else TEMPERATURE_LOW_C
        findings.append(finding(
            f"temperature.{direction}", "temperature", "high" if extreme else "moderate",
            f"Latest temperature reading is {direction} against the monitoring threshold",
            f"The reading on {latest.observation_date.isoformat()} was "
            f"{latest.temperature_c} C, {'at or above' if direction == 'high' else 'at or below'} "
            f"the configured monitoring threshold of {threshold} C.",
            {"observation_id": latest.id, "temperature_c": latest.temperature_c,
             "observation_date": latest.observation_date.isoformat(),
             "threshold_c": threshold, "direction": direction,
             "monitoring_range_c": [TEMPERATURE_LOW_C, TEMPERATURE_HIGH_C],
             "note": "Monitoring threshold, not a clinical diagnosis."},
            "Re-check the temperature and pass the reading to the vet.",
        ))

    if len(outside) >= TEMPERATURE_REPEATED_COUNT:
        findings.append(finding(
            "temperature.repeated_abnormal", "temperature", "high",
            "Several readings outside the monitoring range",
            f"{len(outside)} of {len(points)} readings in the last "
            f"{TEMPERATURE_WINDOW_DAYS} days were outside "
            f"{TEMPERATURE_LOW_C}-{TEMPERATURE_HIGH_C} C.",
            {"abnormal_count": len(outside), "total_readings": len(points),
             "readings": [{"date": r.observation_date.isoformat(),
                           "temperature_c": r.temperature_c} for r in outside],
             "threshold_count": TEMPERATURE_REPEATED_COUNT},
            "Share the full series of readings with the vet.",
        ))

    for before, after in zip(points, points[1:]):
        gap = _days(after.observation_date, before.observation_date)
        delta = round(after.temperature_c - before.temperature_c, 2)
        if gap <= TEMPERATURE_SUDDEN_CHANGE_DAYS and abs(delta) >= TEMPERATURE_SUDDEN_CHANGE_C:
            findings.append(finding(
                "temperature.sudden_change", "temperature", "moderate",
                "Temperature changed sharply between readings",
                f"Temperature moved by {delta} C between "
                f"{before.observation_date.isoformat()} and "
                f"{after.observation_date.isoformat()} ({gap} days).",
                {"from_temperature_c": before.temperature_c, "to_temperature_c": after.temperature_c,
                 "from_date": before.observation_date.isoformat(),
                 "to_date": after.observation_date.isoformat(), "days_between": gap,
                 "change_c": delta, "threshold_c": TEMPERATURE_SUDDEN_CHANGE_C},
                "Re-check the temperature to confirm the readings.",
            ))
            break

    if len(points) < 2:
        quality.append(quality_finding(
            "temperature.insufficient_data", "temperature",
            "Only one temperature reading",
            f"1 reading in the last {TEMPERATURE_WINDOW_DAYS} days is not enough to "
            "compare readings over time.",
            series,
            "Record temperature at each check so readings can be compared.",
        ))
    elif not outside:
        signals.append(signal(
            "temperature.within_range", "temperature", "Temperature readings within range",
            f"All {len(points)} readings in the last {TEMPERATURE_WINDOW_DAYS} days were "
            f"between {TEMPERATURE_LOW_C} and {TEMPERATURE_HIGH_C} C.",
            series,
        ))
    return findings, quality, signals, series


def check_records(records: list[MedicalRecord], follow_ups, today: date):
    findings, quality, signals = [], [], []

    if not records:
        quality.append(quality_finding(
            "medical_record.none_recorded", "medical_record", "No medical records",
            "No veterinary visit or treatment has been recorded for this dog.",
            {"record_count": 0},
            "Add the visit history if there is any.",
        ))
        return findings, quality, signals

    def follow_up_after(day: date) -> bool:
        """Any follow-up arranged on or after `day` — that is the only
        structured evidence that aftercare was organised."""
        return any(f.due_date >= day or (f.completed_date and f.completed_date >= day)
                   for f in follow_ups)

    latest = max(records, key=lambda r: (r.visit_date, r.id))
    since = _days(today, latest.visit_date)

    if 0 <= since <= RECORD_RECENT_DAYS and not follow_up_after(latest.visit_date):
        findings.append(finding(
            "medical_record.recent_visit_no_follow_up", "medical_record", "low",
            "Recent visit with no follow-up recorded",
            f"'{latest.title}' on {latest.visit_date.isoformat()} ({since} days ago) has no "
            "follow-up recorded on or after that date.",
            {"record_id": latest.id, "title": latest.title, "record_type": latest.record_type,
             "visit_date": latest.visit_date.isoformat(), "days_since_visit": since,
             "recent_window_days": RECORD_RECENT_DAYS},
            "Record a follow-up if one was arranged, or note that none is needed.",
        ))

    for row in records:
        age = _days(today, row.visit_date)
        if (row.record_type in RECORD_FOLLOW_UP_EXPECTED_TYPES
                and 0 <= age <= RECORD_FOLLOW_UP_EXPECTED_DAYS
                and not follow_up_after(row.visit_date)):
            findings.append(finding(
                "medical_record.no_follow_up_after_treatment", "medical_record", "moderate",
                f"No follow-up recorded after a {row.record_type} record",
                f"'{row.title}' ({row.record_type}) on {row.visit_date.isoformat()} has no "
                f"follow-up recorded on or after that date. Record types "
                f"{sorted(RECORD_FOLLOW_UP_EXPECTED_TYPES)} are treated as usually having "
                "aftercare; this reflects the records only.",
                {"record_id": row.id, "title": row.title, "record_type": row.record_type,
                 "visit_date": row.visit_date.isoformat(), "days_since_visit": age,
                 "expected_types": sorted(RECORD_FOLLOW_UP_EXPECTED_TYPES),
                 "within_days": RECORD_FOLLOW_UP_EXPECTED_DAYS},
                "Check whether aftercare was arranged and record it.",
            ))
            break

    window = [r for r in records if 0 <= _days(today, r.visit_date) <= RECORD_REPEATED_WINDOW_DAYS]
    if len(window) >= RECORD_REPEATED_COUNT:
        findings.append(finding(
            "medical_record.repeated_visits", "medical_record", "moderate",
            f"{len(window)} visits recorded in {RECORD_REPEATED_WINDOW_DAYS} days",
            f"{len(window)} medical records fall within the last "
            f"{RECORD_REPEATED_WINDOW_DAYS} days.",
            {"record_count": len(window), "window_days": RECORD_REPEATED_WINDOW_DAYS,
             "threshold": RECORD_REPEATED_COUNT,
             "records": [{"date": r.visit_date.isoformat(), "title": r.title,
                          "record_type": r.record_type} for r in window]},
            "Review the recent visits together.",
        ))

    if 0 <= since <= RECORD_RECENT_DAYS:
        signals.append(signal(
            "medical_record.recent_visit", "medical_record", "Recent veterinary record on file",
            f"'{latest.title}' was recorded on {latest.visit_date.isoformat()}.",
            {"record_id": latest.id, "days_since_visit": since},
        ))
    return findings, quality, signals


def check_observation_coverage(observations, today: date):
    """Whether anything is being recorded at all, and how recently."""
    quality = []
    if not observations:
        quality.append(quality_finding(
            "observation.none_recorded", "observation", "No health observations",
            "No weight, temperature or symptom observation has been recorded.",
            {"observation_count": 0},
            "Record observations so trends can be followed.",
        ))
        return quality, None

    latest = max(observations, key=lambda r: (r.observation_date, r.id))
    days = _days(today, latest.observation_date)
    if days > OBSERVATION_STALE_DAYS:
        quality.append(quality_finding(
            "observation.stale", "observation", "No recent observations",
            f"The most recent observation is {days} days old, beyond the "
            f"{OBSERVATION_STALE_DAYS}-day threshold.",
            {"latest_observation_date": latest.observation_date.isoformat(),
             "days_since": days, "threshold_days": OBSERVATION_STALE_DAYS},
            "Record a current observation.",
        ))
    return quality, days


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def score_findings(findings: list[dict]) -> int:
    """Sum of each finding's severity points, capped. Nothing else."""
    return min(MAX_RISK_SCORE, sum(f["points"] for f in findings))


def risk_level(score: int, findings: list[dict]) -> str:
    """The score's band, or the worst single finding's level if that is higher."""
    band = RISK_BANDS[0][1]
    for threshold, name in RISK_BANDS:
        if score >= threshold:
            band = name
    if not findings:
        return band
    worst = max(findings, key=lambda f: SEVERITY_ORDER.index(f["severity"]))["severity"]
    return max(band, SEVERITY_TO_LEVEL[worst], key=SEVERITY_ORDER.index)


def data_quality_score(quality_findings: list[dict]) -> int:
    return max(0, MAX_RISK_SCORE - DATA_QUALITY_PENALTY * len(quality_findings))


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def detect_ml_anomalies(observations) -> dict:
    """The machine-learning layer's view of the observation history.

    Kept behind a function so the rules above stay free of it, and so a model
    problem can never break them: anything that goes wrong comes back as
    `available: False` with a reason.
    """
    try:
        from ml import health_anomaly_service
    except Exception:  # pragma: no cover - only if sklearn/joblib are broken
        return {"available": False, "reason": "model_unavailable", "anomalies": []}
    return health_anomaly_service.analyse_observations(observations)


def analyse(dog, *, vaccinations, medications, observations, follow_ups, records,
            today: date | None = None, generated_at: datetime | None = None,
            ml_detector=None) -> dict:
    """Run every rule over one dog's records.

    Pure: it reads the rows it is given and returns a dict. `today` and
    `generated_at` are injectable so a result can be reproduced exactly.

    `ml_detector` is the anomaly layer, injectable for tests. Its output is
    reported alongside the rules in `ml_anomalies` and **never** changes the
    risk score: the score means the same thing it did before this layer
    existed, and a model change can never move it.
    """
    today = today or date.today()
    findings, quality, signals = [], [], []

    for group in (
        check_vaccinations(vaccinations, today),
        check_medications(medications, today),
        check_follow_ups(follow_ups, today),
        check_records(records, follow_ups, today),
    ):
        findings += group[0]
        quality += group[1]
        signals += group[2]

    weight_found, weight_quality, weight_signals, weight = check_weight(observations, today)
    temp_found, temp_quality, temp_signals, temperature = check_temperature(observations, today)
    findings += weight_found + temp_found
    quality += weight_quality + temp_quality
    signals += weight_signals + temp_signals

    coverage_quality, days_since_observation = check_observation_coverage(observations, today)
    quality += coverage_quality

    findings.sort(key=lambda f: (-SEVERITY_ORDER.index(f["severity"]), f["code"]))
    score = score_findings(findings)

    by_severity = {name: sum(1 for f in findings if f["severity"] == name)
                   for name in reversed(SEVERITY_ORDER)}

    return {
        "dog_id": dog.id,
        "dog_name": dog.name,
        "risk_level": risk_level(score, findings),
        "risk_score": score,
        "score_breakdown": {
            "points_by_finding": [
                {"code": f["code"], "severity": f["severity"], "points": f["points"]}
                for f in findings
            ],
            "total_before_cap": sum(f["points"] for f in findings),
            "max_score": MAX_RISK_SCORE,
            "severity_points": dict(SEVERITY_POINTS),
        },
        "finding_counts": {"total": len(findings), **by_severity},
        "findings": findings,
        "positive_signals": signals,
        # Separate on purpose. These come from a model, are scored on a
        # different scale, and contribute nothing to risk_score above.
        "ml_anomalies": (ml_detector or detect_ml_anomalies)(observations),
        "data_quality": {
            "score": data_quality_score(quality),
            "findings": quality,
            "counts": {
                "vaccinations": len(vaccinations), "medications": len(medications),
                "observations": len(observations), "follow_ups": len(follow_ups),
                "medical_records": len(records),
            },
            "days_since_last_observation": days_since_observation,
            "weight_series": weight,
            "temperature_series": temperature,
        },
        "analysis_date": today.isoformat(),
        "generated_at": (generated_at or datetime.now(timezone.utc)).isoformat(timespec="seconds"),
        "method": "deterministic rule engine (no machine learning)",
        "disclaimer": (
            "Patterns in recorded data, to help staff decide what to look at. "
            "Not a diagnosis and not veterinary advice."
        ),
        "config": config(),
    }


def analyse_dog(dog, today: date | None = None, generated_at: datetime | None = None,
                ml_detector=None) -> dict:
    """Load a dog's records through its relationships and analyse them."""
    return analyse(
        dog,
        ml_detector=ml_detector,
        vaccinations=list(dog.vaccinations),
        medications=list(dog.medications),
        observations=list(dog.health_observations),
        follow_ups=list(dog.follow_ups),
        records=list(dog.medical_records),
        today=today,
        generated_at=generated_at,
    )


def summarise(analysis: dict, top: int = 3) -> dict:
    """The headline only: level, score, counts and the most severe findings."""
    return {
        "dog_id": analysis["dog_id"],
        "dog_name": analysis["dog_name"],
        "risk_level": analysis["risk_level"],
        "risk_score": analysis["risk_score"],
        "finding_counts": analysis["finding_counts"],
        "data_quality_score": analysis["data_quality"]["score"],
        "data_quality_finding_count": len(analysis["data_quality"]["findings"]),
        "top_findings": [
            {k: f[k] for k in ("code", "category", "severity", "title", "reason", "recommendation")}
            for f in analysis["findings"][:top]
        ],
        "positive_signal_count": len(analysis["positive_signals"]),
        "ml_anomalies": {
            "available": analysis["ml_anomalies"].get("available", False),
            "reason": analysis["ml_anomalies"].get("reason"),
            "anomaly_count": analysis["ml_anomalies"].get("anomaly_count", 0),
            "model_version": analysis["ml_anomalies"].get("model_version"),
        },
        "analysis_date": analysis["analysis_date"],
        "generated_at": analysis["generated_at"],
        "method": analysis["method"],
        "disclaimer": analysis["disclaimer"],
    }
