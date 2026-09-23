"""Turning health-intelligence findings into alerts that can be worked on.

health_intelligence.py decides what is wrong; this module decides what to write
down, and tracks it until someone resolves it. No rule, severity or score is
recalculated here — every value is copied from the finding as produced.

Identity
--------
A finding is identified by (dog_id, finding_code, entity_key), where
entity_key names the record it is about ("follow_up_id:7") or is empty for
findings about a series, such as a weight trend. Two overdue follow-ups are
therefore two alerts, while the same overdue follow-up seen on twenty syncs is
one alert seen twenty times.

Lifecycle
---------
    open --acknowledge--> acknowledged --resolve--> resolved  (terminal)
      \\------------------ resolve ------------------/

Sync rules
----------
* Finding present, active alert exists  -> update it: last_detected_at,
  detection_count, and the wording/evidence/severity from the current finding.
  first_detected_at and risk_score_at_detection never change.
* Finding present, no active alert      -> create one. If a resolved alert with
  the same identity exists, the new row links back to it through
  reopened_from_id and counts as "reopened" rather than "created".
* Finding gone, active alert exists     -> resolve it automatically, with
  auto_resolved set and no resolving user. Nothing is ever deleted.

Resolved rows are never reused or edited, so an acknowledgement or a
resolution note written by a person cannot be overwritten by a later sync.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import func
from sqlalchemy.orm import joinedload

import health_intelligence
import notification_service
from models import ALERT_ACTIVE_STATUSES, HealthAlert, db, utcnow

# Findings at or above this severity are persisted. Everything the engine
# produces is worth recording; the threshold for *notifying* is separate and
# lives in notification_service.
ALERT_MIN_SEVERITY = "low"
SEVERITY_ORDER = health_intelligence.SEVERITY_ORDER

# Evidence fields that identify the record a finding is about, in the order
# they are looked for.
ENTITY_FIELDS = (
    "follow_up_id", "vaccination_id", "medication_id", "record_id", "observation_id",
)

AUTO_RESOLUTION_NOTE = "Automatically resolved: the finding was no longer present at sync."


def _with_related(query):
    """Load the rows to_dict() needs in the same query.

    Every alert reports its dog's name and, once reviewed, who acknowledged or
    resolved it. Left lazy, listing N alerts costs N extra round trips — which
    is exactly what the admin queue does on every page load.
    """
    return query.options(
        joinedload(HealthAlert.dog),
        joinedload(HealthAlert.acknowledged_by),
        joinedload(HealthAlert.resolved_by),
    )


def entity_key(finding: dict) -> str:
    """Which record this finding is about, or "" for a whole-series finding."""
    evidence = finding.get("evidence") or {}
    for field in ENTITY_FIELDS:
        if evidence.get(field) is not None:
            return f"{field}:{evidence[field]}"
    return ""


def fingerprint(dog_id: int, finding: dict) -> tuple:
    """The stable identity of a finding, used for deduplication."""
    return (dog_id, finding["code"], entity_key(finding))


def _alert_key(alert: HealthAlert) -> tuple:
    return (alert.dog_id, alert.finding_code, alert.entity_key or "")


def active_alerts(dog_id: int) -> list[HealthAlert]:
    return (
        _with_related(
            HealthAlert.query.filter(
                HealthAlert.dog_id == dog_id,
                HealthAlert.status.in_(ALERT_ACTIVE_STATUSES),
            )
        )
        .order_by(HealthAlert.last_detected_at.desc())
        .all()
    )


def _latest_resolved(dog_id: int, finding_code: str, key: str) -> HealthAlert | None:
    return (
        HealthAlert.query.filter_by(
            dog_id=dog_id, finding_code=finding_code, entity_key=key, status="resolved"
        )
        .order_by(HealthAlert.resolved_at.desc(), HealthAlert.id.desc())
        .first()
    )


def _apply_finding(alert: HealthAlert, finding: dict) -> None:
    """Copy the current wording and evidence onto an alert.

    Severity is refreshed too: the same follow-up drifts from moderate to high
    as it stays overdue, and the alert should say what is true now. The
    detection-time score is untouched.
    """
    alert.category = finding["category"]
    alert.severity = finding["severity"]
    alert.title = finding["title"]
    alert.reason = finding["reason"]
    alert.evidence = finding.get("evidence") or {}
    alert.recommendation = finding.get("recommendation")


ML_FINDING_CODE = "ml.health_anomaly"

# Only the model's strongest anomalies are written down. An anomaly is a
# "worth a look", not a rule that was broken, so alerting on every one would
# bury the deterministic findings that state exactly what is wrong.
ML_ALERTABLE_SEVERITY = "high"

# ...and they are recorded at this severity, whatever the model's own band.
# Deliberately below the deterministic highs: a missed follow-up is a fact,
# an unusual weight reading is a suggestion, and the queue should sort them
# that way. It still clears the notification threshold.
ML_ALERT_SEVERITY = "moderate"


def ml_findings(analysis: dict) -> list[dict]:
    """The model's anomalies, shaped like findings so the same lifecycle
    applies — deduplication, reopening, resolution and all.

    They keep their own code and category, so an ML alert is never mistaken
    for a deterministic one in the queue or in the database.
    """
    ml = analysis.get("ml_anomalies") or {}
    if not ml.get("available"):
        return []

    findings = []
    for anomaly in ml.get("anomalies", []):
        if anomaly["severity"] != ML_ALERTABLE_SEVERITY:
            continue
        reasons = anomaly["reasons"]
        findings.append({
            "code": ML_FINDING_CODE,
            "category": "ml_anomaly",
            "severity": ML_ALERT_SEVERITY,
            "title": f"Unusual observation pattern on {anomaly['observation_date']}",
            "reason": (
                " ".join(reasons)
                if reasons
                else "This observation does not match the dog's recent pattern."
            ) + " Flagged by the anomaly model for review; this is not a diagnosis.",
            "evidence": {
                # observation_id makes each flagged observation its own alert,
                # so a second unusual reading does not overwrite the first.
                "observation_id": anomaly["observation_id"],
                "observation_date": anomaly["observation_date"],
                "anomaly_score": anomaly["anomaly_score"],
                "model_severity": anomaly["severity"],
                "model_version": anomaly["model_version"],
                "measurements_considered": anomaly["measurements_considered"],
                "reasons": reasons,
                **anomaly["evidence"],
            },
            "recommendation": (
                "Review this observation against the dog's history and confirm "
                "whether it needs veterinary attention."
            ),
            "points": 0,  # never contributes to the deterministic risk score
        })
    return findings


def sync_dog_alerts(dog, *, today: date | None = None, now: datetime | None = None) -> dict:
    """Run the analysis and bring this dog's alerts in line with it.

    Idempotent: with unchanged records, a second call creates nothing and only
    moves last_detected_at forward.
    """
    now = now or utcnow()
    analysis = health_intelligence.analyse_dog(dog, today=today)
    score = analysis["risk_score"]

    findings = [
        f for f in analysis["findings"]
        if SEVERITY_ORDER.index(f["severity"]) >= SEVERITY_ORDER.index(ALERT_MIN_SEVERITY)
    ] + ml_findings(analysis)

    existing = {_alert_key(a): a for a in active_alerts(dog.id)}
    created, updated, reopened, resolved = [], [], [], []
    seen: set[tuple] = set()

    for finding in findings:
        key = fingerprint(dog.id, finding)
        if key in seen:
            # Two findings with the same identity would collide on the unique
            # index. The engine does not currently produce any, and if it ever
            # did, the first wins rather than the sync failing.
            continue
        seen.add(key)

        alert = existing.get(key)
        if alert is not None:
            was = alert.severity
            _apply_finding(alert, finding)
            alert.last_detected_at = now
            alert.detection_count += 1
            updated.append(alert)
            if SEVERITY_ORDER.index(alert.severity) > SEVERITY_ORDER.index(was):
                notification_service.emit_health_alert(
                    alert, event="escalated", previous_severity=was
                )
            continue

        prior = _latest_resolved(dog.id, finding["code"], key[2])
        alert = HealthAlert(
            dog_id=dog.id,
            finding_code=finding["code"],
            entity_key=key[2],
            risk_score_at_detection=score,
            status="open",
            first_detected_at=now,
            last_detected_at=now,
            detection_count=1,
            reopened_from_id=prior.id if prior else None,
        )
        _apply_finding(alert, finding)
        db.session.add(alert)
        # Flush so the notification can carry the alert's id.
        db.session.flush()
        (reopened if prior else created).append(alert)
        notification_service.emit_health_alert(
            alert, event="reopened" if prior else "created"
        )

    # Anything still active that the analysis no longer reports is closed off,
    # not deleted.
    for key, alert in existing.items():
        if key not in seen:
            alert.status = "resolved"
            alert.resolved_at = now
            alert.resolved_by_id = None
            alert.auto_resolved = True
            alert.resolution_note = AUTO_RESOLUTION_NOTE
            resolved.append(alert)

    db.session.commit()

    return {
        "dog_id": dog.id,
        "dog_name": dog.name,
        "created": len(created),
        "updated": len(updated),
        "reopened": len(reopened),
        "resolved": len(resolved),
        "risk_score": score,
        "risk_level": analysis["risk_level"],
        "analysis_date": analysis["analysis_date"],
        "alerts": [a.to_dict() for a in active_alerts(dog.id)],
        "auto_resolved_alerts": [a.to_dict() for a in resolved],
    }


# --------------------------------------------------------------------------- #
# Admin workflow
# --------------------------------------------------------------------------- #
class AlertError(Exception):
    """A lifecycle transition that is not allowed; the message is shown to the
    caller as a 400."""


def acknowledge(alert: HealthAlert, user, now: datetime | None = None) -> HealthAlert:
    if alert.status == "resolved":
        raise AlertError(
            "This alert is already resolved. A resolved alert is history and is not "
            "reopened by hand; it reappears as a new alert if the finding returns."
        )
    if alert.status == "acknowledged":
        raise AlertError(
            f"This alert was already acknowledged"
            f"{' by ' + alert.acknowledged_by.name if alert.acknowledged_by else ''}."
        )
    alert.status = "acknowledged"
    alert.acknowledged_at = now or utcnow()
    alert.acknowledged_by_id = user.id
    db.session.commit()
    return alert


def resolve(alert: HealthAlert, user, note: str | None = None,
            now: datetime | None = None) -> HealthAlert:
    if alert.status == "resolved":
        raise AlertError("This alert is already resolved.")
    alert.status = "resolved"
    alert.resolved_at = now or utcnow()
    alert.resolved_by_id = user.id
    alert.auto_resolved = False
    if note:
        alert.resolution_note = note
    db.session.commit()
    return alert


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #
def for_dog(dog_id: int, status: str | None = None) -> dict:
    """One dog's alerts, grouped by status. `status` narrows it to one group."""
    query = _with_related(HealthAlert.query.filter_by(dog_id=dog_id))
    if status:
        query = query.filter_by(status=status)
    rows = query.order_by(
        HealthAlert.last_detected_at.desc(), HealthAlert.id.desc()
    ).all()

    grouped = {name: [a.to_dict() for a in rows if a.status == name]
               for name in ("open", "acknowledged", "resolved")}
    return {
        "dog_id": dog_id,
        "count": len(rows),
        "counts": {name: len(items) for name, items in grouped.items()},
        **grouped,
    }


def totals() -> dict:
    """Counts for the dashboard header, aggregated in the database.

    Always over every alert, whatever the caller filtered the list by — the
    header reports the whole queue, not the current page.
    """
    by_status = dict(
        db.session.query(HealthAlert.status, func.count(HealthAlert.id))
        .group_by(HealthAlert.status)
        .all()
    )
    by_severity_active = dict(
        db.session.query(HealthAlert.severity, func.count(HealthAlert.id))
        .filter(HealthAlert.status.in_(ALERT_ACTIVE_STATUSES))
        .group_by(HealthAlert.severity)
        .all()
    )
    return {
        "open": by_status.get("open", 0),
        "acknowledged": by_status.get("acknowledged", 0),
        "resolved": by_status.get("resolved", 0),
        "total": sum(by_status.values()),
        # Severity of everything still needing attention, which is what the
        # "critical / high / moderate / low" tiles count.
        "active_by_severity": {
            name: by_severity_active.get(name, 0) for name in reversed(SEVERITY_ORDER)
        },
    }


def queue(status=None, severity=None, dog_id=None, limit: int = 100) -> dict:
    """The admin queue: every dog's alerts, most severe and most recent first."""
    query = _with_related(HealthAlert.query)
    if status:
        query = query.filter(HealthAlert.status.in_(status))
    if severity:
        query = query.filter(HealthAlert.severity.in_(severity))
    if dog_id:
        query = query.filter(HealthAlert.dog_id == dog_id)

    rows = query.all()
    rows.sort(key=lambda a: (-SEVERITY_ORDER.index(a.severity), -a.last_detected_at.timestamp()))
    return {
        "count": len(rows),
        "returned": len(rows[:limit]),
        "filters": {"status": status, "severity": severity, "dog_id": dog_id, "limit": limit},
        "totals": totals(),
        "alerts": [a.to_dict() for a in rows[:limit]],
    }
