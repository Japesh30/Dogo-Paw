"""Medical-record API: /api/dogs/<dog_id>/medical/... and the admin alert queue.

Storage, retrieval and routing only. The analysis lives in
health_intelligence.py and the alert lifecycle in health_alerts.py; the
handlers here call them and return what they produce.

Access:
    GET   (summary, lists, analysis, alerts)  any signed-in user -> 401 anonymous
    POST  (create, alert sync)                admin only         -> 403 otherwise
    PATCH (correct/update, alert review)      admin only
There is no DELETE: a medical history is corrected, not erased, and alerts are
resolved rather than removed.

Every record type is described once in RESOURCES (its model, how each field is
validated, and the rules that span fields), and the same four handlers serve
all five of them.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Callable

from flask import Blueprint, g, jsonify, request

import health_alerts
import health_intelligence
from auth import admin_required, login_required
from models import (
    ALERT_SEVERITIES,
    ALERT_STATUSES,
    FOLLOW_UP_STATUSES,
    MAX_WEIGHT_KG,
    MEDICAL_RECORD_TYPES,
    MEDICATION_STATUSES,
    TEMPERATURE_RANGE_C,
    VACCINATION_STATUSES,
    Dog,
    FollowUp,
    HealthAlert,
    HealthObservation,
    MedicalRecord,
    Medication,
    Vaccination,
    db,
)

bp = Blueprint("medical", __name__, url_prefix="/api/dogs/<int:dog_id>/medical")

MAX_NOTES = 2000        # notes / description: TEXT, but bounded like every other free-text field
MAX_SYMPTOMS = 20
MAX_SYMPTOM = 80
SUMMARY_RECENT = 10     # observations and visit records shown in the summary

# A date entered in India late in the evening is "tomorrow" in UTC, which is
# what the server's date.today() may be; one day of slack stops that being
# rejected as a future date.
FUTURE_GRACE = timedelta(days=1)


class Invalid(ValueError):
    """A field failed validation; the message goes back to the caller as a 400."""


def error(message: str, status: int = 400):
    return jsonify({"error": message}), status


# --------------------------------------------------------------------------- #
# Field validators. Each takes the raw JSON value and the field name, and
# returns the value to store or raises Invalid. None / "" mean "not given".
# --------------------------------------------------------------------------- #
Validator = Callable[[object, str], object]


def _blank(value) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def text(limit: int, required: bool = False) -> Validator:
    def validate(value, name):
        if _blank(value):
            if required:
                raise Invalid(f"'{name}' is required.")
            return None
        if not isinstance(value, str):
            raise Invalid(f"'{name}' must be text.")
        value = value.strip()
        if len(value) > limit:
            raise Invalid(f"'{name}' is too long (max {limit} characters).")
        return value

    return validate


def day(required: bool = False, past_only: bool = False) -> Validator:
    def validate(value, name):
        if _blank(value):
            if required:
                raise Invalid(f"'{name}' is required.")
            return None
        if not isinstance(value, str):
            raise Invalid(f"'{name}' must be a date in YYYY-MM-DD format.")
        try:
            parsed = date.fromisoformat(value.strip())
        except ValueError:
            raise Invalid(f"'{name}' must be a valid date in YYYY-MM-DD format.") from None
        if parsed.year < 1990:
            raise Invalid(f"'{name}' is implausibly far in the past.")
        if past_only and parsed > date.today() + FUTURE_GRACE:
            raise Invalid(f"'{name}' cannot be in the future.")
        return parsed

    return validate


def choice(allowed: frozenset, required: bool = True) -> Validator:
    def validate(value, name):
        if _blank(value):
            if required:
                raise Invalid(f"'{name}' is required.")
            return None
        normalised = value.strip().lower() if isinstance(value, str) else None
        if normalised not in allowed:
            raise Invalid(f"'{name}' must be one of: {', '.join(sorted(allowed))}.")
        return normalised

    return validate


def number(low: float, high: float, low_exclusive: bool, unit: str) -> Validator:
    def validate(value, name):
        if value is None:
            return None
        # bool is an int subclass; `true` is not a weight.
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise Invalid(f"'{name}' must be a number.")
        value = float(value)
        if value != value or value in (float("inf"), float("-inf")):
            raise Invalid(f"'{name}' must be a finite number.")
        too_low = value <= low if low_exclusive else value < low
        if too_low or value > high:
            bound = f"greater than {low:g}" if low_exclusive else f"at least {low:g}"
            raise Invalid(f"'{name}' must be {bound} and at most {high:g} {unit}.")
        return round(value, 2)

    return validate


def symptoms(value, name):
    if value is None:
        return None
    if not isinstance(value, list):
        raise Invalid(f"'{name}' must be a list of short descriptions.")
    if len(value) > MAX_SYMPTOMS:
        raise Invalid(f"'{name}' can hold at most {MAX_SYMPTOMS} entries.")
    cleaned = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise Invalid(f"Every entry in '{name}' must be non-empty text.")
        item = item.strip().lower()
        if len(item) > MAX_SYMPTOM:
            raise Invalid(f"Each entry in '{name}' must be at most {MAX_SYMPTOM} characters.")
        if item not in cleaned:
            cleaned.append(item)
    return cleaned or None


# --------------------------------------------------------------------------- #
# Rules that involve more than one field. They see the record as it would be
# after the change (existing values merged with the new ones), so a PATCH that
# changes one field is still checked against the others.
# --------------------------------------------------------------------------- #
def _no_rules(_: dict) -> None:
    return None


def _vaccination_rules(r: dict) -> None:
    if r["status"] == "completed" and r["administered_date"] is None:
        raise Invalid("A completed vaccination needs an 'administered_date'.")
    if r["status"] in {"scheduled", "overdue"} and r["next_due_date"] is None:
        raise Invalid(f"A {r['status']} vaccination needs a 'next_due_date'.")
    if (r["administered_date"] and r["next_due_date"]
            and r["next_due_date"] < r["administered_date"]):
        raise Invalid("'next_due_date' cannot be before 'administered_date'.")


def _medication_rules(r: dict) -> None:
    if r["end_date"] and r["end_date"] < r["start_date"]:
        raise Invalid("'end_date' cannot be before 'start_date'.")
    if r["status"] in {"completed", "discontinued"} and r["end_date"] is None:
        raise Invalid(f"A {r['status']} medication needs an 'end_date'.")


def _observation_rules(r: dict) -> None:
    if r["weight_kg"] is None and r["temperature_c"] is None and not r["symptoms"]:
        raise Invalid(
            "An observation needs at least one of 'weight_kg', 'temperature_c' or 'symptoms'."
        )


def _follow_up_rules(r: dict) -> None:
    if r["status"] == "completed" and r["completed_date"] is None:
        raise Invalid("A completed follow-up needs a 'completed_date'.")
    if r["status"] != "completed" and r["completed_date"] is not None:
        raise Invalid("'completed_date' is only allowed when status is 'completed'.")


# --------------------------------------------------------------------------- #
# The five record types. `order` is newest-first for events, soonest-first for
# things that are due.
# --------------------------------------------------------------------------- #
RESOURCES = {
    "records": {
        "model": MedicalRecord,
        "fields": {
            "record_type": choice(MEDICAL_RECORD_TYPES),
            "title": text(160, required=True),
            "description": text(MAX_NOTES),
            "veterinarian": text(120),
            "visit_date": day(required=True, past_only=True),
        },
        "rules": _no_rules,
        "order": (MedicalRecord.visit_date.desc(), MedicalRecord.id.desc()),
    },
    "vaccinations": {
        "model": Vaccination,
        "fields": {
            "vaccine_name": text(120, required=True),
            "administered_date": day(past_only=True),
            "next_due_date": day(),
            "status": choice(VACCINATION_STATUSES),
            "veterinarian": text(120),
            "notes": text(MAX_NOTES),
        },
        "rules": _vaccination_rules,
        "order": (Vaccination.administered_date.desc(), Vaccination.id.desc()),
    },
    "medications": {
        "model": Medication,
        "fields": {
            "medication_name": text(120, required=True),
            "dosage": text(80, required=True),
            "frequency": text(80, required=True),
            "start_date": day(required=True),
            "end_date": day(),
            "status": choice(MEDICATION_STATUSES),
            "prescribed_by": text(120),
            "notes": text(MAX_NOTES),
        },
        "rules": _medication_rules,
        "order": (Medication.start_date.desc(), Medication.id.desc()),
    },
    "observations": {
        "model": HealthObservation,
        "fields": {
            "observation_date": day(required=True, past_only=True),
            "weight_kg": number(0, MAX_WEIGHT_KG, low_exclusive=True, unit="kg"),
            "temperature_c": number(*TEMPERATURE_RANGE_C, low_exclusive=False, unit="°C"),
            "symptoms": symptoms,
            "notes": text(MAX_NOTES),
        },
        "rules": _observation_rules,
        "order": (HealthObservation.observation_date.desc(), HealthObservation.id.desc()),
    },
    "follow-ups": {
        "model": FollowUp,
        "fields": {
            "reason": text(200, required=True),
            "due_date": day(required=True),
            "completed_date": day(past_only=True),
            "status": choice(FOLLOW_UP_STATUSES),
            "notes": text(MAX_NOTES),
        },
        "rules": _follow_up_rules,
        "order": (FollowUp.due_date, FollowUp.id),
    },
}


def parse(resource: dict, data: dict, current=None) -> dict:
    """Validate a create (current=None) or a partial update of `current`.

    Returns only the fields to write. Unknown keys are ignored, as elsewhere in
    the API; `dog_id`, `id` and timestamps are never taken from the body.
    """
    fields = resource["fields"]
    values = {}
    for name, validate in fields.items():
        if name in data:
            values[name] = validate(data[name], name)
        elif current is None:
            # Not sent: required fields fail here, optional ones become None.
            values[name] = validate(None, name)

    merged = {name: getattr(current, name) for name in fields} if current else {}
    merged.update(values)
    resource["rules"](merged)
    return values


# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #
def _dog_or_404(dog_id: int):
    dog = db.session.get(Dog, dog_id)
    return dog, (None if dog else error(f"No dog with id {dog_id}.", 404))


def _resource_or_404(kind: str):
    resource = RESOURCES.get(kind)
    if resource is None:
        return None, error(
            f"Unknown medical record type '{kind}'. Use one of: {', '.join(RESOURCES)}.", 404
        )
    return resource, None


def _body():
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else None


def _rows(resource: dict, dog_id: int, limit: int | None = None) -> list[dict]:
    model = resource["model"]
    query = model.query.filter_by(dog_id=dog_id).order_by(*resource["order"])
    if limit:
        query = query.limit(limit)
    return [row.to_dict() for row in query.all()]


@bp.get("")
@login_required
def summary(dog_id: int):
    """Everything on file for one dog, structured for the later analysis layer.

    Reports what is recorded and nothing more: no score, no healthy/unhealthy
    label, no derived status.
    """
    dog, err = _dog_or_404(dog_id)
    if err:
        return err

    counts = {
        resource["model"].__tablename__: resource["model"].query.filter_by(dog_id=dog_id).count()
        for resource in RESOURCES.values()
    }
    return jsonify(
        {
            "dog": dog.to_dict(),
            "vaccinations": _rows(RESOURCES["vaccinations"], dog_id),
            "medications": _rows(RESOURCES["medications"], dog_id),
            "recent_observations": _rows(RESOURCES["observations"], dog_id, SUMMARY_RECENT),
            "follow_ups": _rows(RESOURCES["follow-ups"], dog_id),
            "recent_medical_records": _rows(RESOURCES["records"], dog_id, SUMMARY_RECENT),
            "counts": counts,
        }
    )


@bp.post("/health-alerts/sync")
@admin_required
def sync_health_alerts(dog_id: int):
    """Re-run the analysis and bring this dog's alerts in line with it.

    Admin-only because it writes medical records, matching every other write in
    this blueprint. Idempotent: unchanged data creates nothing.
    """
    dog, err = _dog_or_404(dog_id)
    if err:
        return err
    return jsonify(health_alerts.sync_dog_alerts(dog))


@bp.get("/health-alerts")
@login_required
def list_health_alerts(dog_id: int):
    """This dog's alerts, grouped by status. `?status=` narrows it to one."""
    _, err = _dog_or_404(dog_id)
    if err:
        return err
    status = request.args.get("status", "").strip().lower() or None
    if status and status not in ALERT_STATUSES:
        return error(f"'status' must be one of: {', '.join(sorted(ALERT_STATUSES))}.")
    return jsonify(health_alerts.for_dog(dog_id, status))


@bp.get("/health-analysis")
@login_required
def health_analysis(dog_id: int):
    """Findings from the deterministic rule engine in health_intelligence.py.

    Same access as the other medical reads. The rules live in that module, not
    here: this handler only loads the dog and returns what it produced.
    """
    dog, err = _dog_or_404(dog_id)
    if err:
        return err
    return jsonify(health_intelligence.analyse_dog(dog))


@bp.get("/health-analysis/summary")
@login_required
def health_analysis_summary(dog_id: int):
    """The headline: level, score, counts and the most severe findings. For a
    list or a badge, where the full evidence payload would be wasted."""
    dog, err = _dog_or_404(dog_id)
    if err:
        return err
    return jsonify(health_intelligence.summarise(health_intelligence.analyse_dog(dog)))


# Registered after the two static paths above so "/health-analysis" is matched
# by them rather than being read as a record type.
@bp.get("/<kind>")
@login_required
def list_items(dog_id: int, kind: str):
    resource, err = _resource_or_404(kind)
    if err:
        return err
    _, err = _dog_or_404(dog_id)
    if err:
        return err
    items = _rows(resource, dog_id)
    return jsonify({"dog_id": dog_id, "type": kind, "count": len(items), "items": items})


@bp.post("/<kind>")
@admin_required
def create_item(dog_id: int, kind: str):
    resource, err = _resource_or_404(kind)
    if err:
        return err
    _, err = _dog_or_404(dog_id)
    if err:
        return err
    data = _body()
    if data is None:
        return error("Send the record as a JSON object.")

    try:
        values = parse(resource, data)
    except Invalid as exc:
        return error(str(exc))

    row = resource["model"](dog_id=dog_id, recorded_by_id=g.current_user.id, **values)
    db.session.add(row)
    db.session.commit()
    return jsonify({"item": row.to_dict()}), 201


@bp.patch("/<kind>/<int:item_id>")
@admin_required
def update_item(dog_id: int, kind: str, item_id: int):
    resource, err = _resource_or_404(kind)
    if err:
        return err
    row = resource["model"].query.filter_by(id=item_id, dog_id=dog_id).first()
    if row is None:
        return error(f"No {kind} entry {item_id} for dog {dog_id}.", 404)
    data = _body()
    if data is None:
        return error("Send the changes as a JSON object.")

    try:
        values = parse(resource, data, current=row)
    except Invalid as exc:
        return error(str(exc))
    if not values:
        return error(f"Nothing to update. Editable fields: {', '.join(resource['fields'])}.")

    for name, value in values.items():
        setattr(row, name, value)
    db.session.commit()
    return jsonify({"item": row.to_dict()})


# --------------------------------------------------------------------------- #
# Admin alert queue. A separate blueprint because these are not scoped to one
# dog; the handlers stay thin and call health_alerts for the work.
# --------------------------------------------------------------------------- #
admin_bp = Blueprint("medical_admin", __name__, url_prefix="/api/admin/health-alerts")

MAX_RESOLUTION_NOTE = 1000
ALERT_ACTIONS = ("acknowledge", "resolve")


def _csv_param(name: str, allowed: frozenset):
    """A repeatable or comma-separated filter, e.g. ?severity=high,critical."""
    raw = ",".join(request.args.getlist(name))
    values = [v.strip().lower() for v in raw.split(",") if v.strip()]
    unknown = [v for v in values if v not in allowed]
    if unknown:
        raise Invalid(
            f"'{name}' must be one of: {', '.join(sorted(allowed))}. Got: {', '.join(unknown)}."
        )
    return values or None


@admin_bp.get("")
@admin_required
def alert_queue():
    """Every dog's alerts, most severe first. Filter by status, severity, dog."""
    try:
        status = _csv_param("status", ALERT_STATUSES)
        severity = _csv_param("severity", ALERT_SEVERITIES)
    except Invalid as exc:
        return error(str(exc))

    dog_id = request.args.get("dog_id")
    if dog_id is not None:
        try:
            dog_id = int(dog_id)
        except ValueError:
            return error("'dog_id' must be a number.")

    try:
        limit = min(500, max(1, int(request.args.get("limit", 100))))
    except ValueError:
        return error("'limit' must be a number.")

    return jsonify(health_alerts.queue(status=status, severity=severity,
                                       dog_id=dog_id, limit=limit))


@admin_bp.patch("/<int:alert_id>")
@admin_required
def review_alert(alert_id: int):
    """Acknowledge or resolve one alert. Alerts are never deleted."""
    alert = db.session.get(HealthAlert, alert_id)
    if alert is None:
        return error(f"No alert with id {alert_id}.", 404)

    data = _body()
    if data is None:
        return error("Send the change as a JSON object.")

    action = data.get("action")
    action = action.strip().lower() if isinstance(action, str) else ""
    if action not in ALERT_ACTIONS:
        return error(f"'action' must be one of: {', '.join(ALERT_ACTIONS)}.")

    note = data.get("resolution_note")
    if note is not None and not isinstance(note, str):
        return error("'resolution_note' must be text.")
    note = note.strip() if isinstance(note, str) else None
    if note and len(note) > MAX_RESOLUTION_NOTE:
        return error(f"'resolution_note' is too long (max {MAX_RESOLUTION_NOTE} characters).")

    try:
        if action == "acknowledge":
            health_alerts.acknowledge(alert, g.current_user)
        else:
            health_alerts.resolve(alert, g.current_user, note)
    except health_alerts.AlertError as exc:
        return error(str(exc), 409)

    return jsonify({"alert": alert.to_dict()})
