"""SQLAlchemy models backing the Dogo-Paw API."""

from __future__ import annotations

from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def utcnow() -> datetime:
    """Naive UTC. SQLite drops tzinfo on write anyway, so storing naive keeps
    what goes in and what comes out identical."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso_utc(value: datetime) -> str:
    """Serialise a stored (naive, UTC) timestamp with an explicit Z so the
    browser does not read it as local time."""
    return f"{value.isoformat(timespec='seconds')}Z"


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    adopter_profiles = db.relationship("Adopter", back_populates="user")
    match_requests = db.relationship("MatchRequest", back_populates="user")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "is_admin": self.is_admin,
            "created_at": iso_utc(self.created_at),
        }


class Dog(db.Model):
    __tablename__ = "dogs"

    # `dog_id` in the source dataset; exposed under that name by the API.
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    age = db.Column(db.Float, nullable=False)
    energy_level = db.Column(db.String(20), nullable=False)  # low|medium|high
    size = db.Column(db.String(20), nullable=False)  # small|medium|large
    temperament = db.Column(db.String(40), nullable=False)
    medical_needs = db.Column(db.Boolean, default=False, nullable=False)
    good_with_kids = db.Column(db.Boolean, default=True, nullable=False)
    good_with_other_pets = db.Column(db.Boolean, default=True, nullable=False)

    # Added in Phase 6 for the public gallery. Nullable so a dog added by hand
    # without either of them still saves; the UI falls back to a drawn avatar
    # and hides an empty bio rather than rendering a gap.
    photo_url = db.Column(db.String(255), nullable=True)
    bio = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    # Medical history. Loaded only when accessed (the default lazy="select"),
    # and deliberately left out of to_dict(): the public dog endpoints must
    # keep returning the profile alone, never someone's clinical record.
    #
    # The cascade is done by the ORM, not left to ON DELETE CASCADE alone
    # (no passive_deletes): SQLite does not enforce foreign keys by default, so
    # relying on the database would orphan medical rows in development.
    medical_records = db.relationship(
        "MedicalRecord", back_populates="dog", cascade="all, delete-orphan",
        order_by="MedicalRecord.visit_date.desc()",
    )
    vaccinations = db.relationship(
        "Vaccination", back_populates="dog", cascade="all, delete-orphan",
        order_by="Vaccination.id",
    )
    medications = db.relationship(
        "Medication", back_populates="dog", cascade="all, delete-orphan",
        order_by="Medication.start_date.desc()",
    )
    health_observations = db.relationship(
        "HealthObservation", back_populates="dog", cascade="all, delete-orphan",
        order_by="HealthObservation.observation_date.desc()",
    )
    follow_ups = db.relationship(
        "FollowUp", back_populates="dog", cascade="all, delete-orphan",
        order_by="FollowUp.due_date",
    )
    health_alerts = db.relationship(
        "HealthAlert", back_populates="dog", cascade="all, delete-orphan",
        order_by="HealthAlert.last_detected_at.desc()",
    )

    def to_dict(self) -> dict:
        return {
            "dog_id": self.id,
            "name": self.name,
            "age": self.age,
            "energy_level": self.energy_level,
            "size": self.size,
            "temperament": self.temperament,
            "medical_needs": self.medical_needs,
            "good_with_kids": self.good_with_kids,
            "good_with_other_pets": self.good_with_other_pets,
            "photo_url": self.photo_url,
            "bio": self.bio,
        }


class Adopter(db.Model):
    """One submitted questionnaire. Kept separate from User because a visitor
    can run the matcher without an account, and a signed-in user can run it
    more than once with different answers."""

    __tablename__ = "adopters"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    activity_level = db.Column(db.String(20), nullable=False)
    home_type = db.Column(db.String(30), nullable=False)
    experience_level = db.Column(db.String(20), nullable=False)
    has_kids = db.Column(db.Boolean, default=False, nullable=False)
    has_other_pets = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    user = db.relationship("User", back_populates="adopter_profiles")
    match_requests = db.relationship("MatchRequest", back_populates="adopter")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "activity_level": self.activity_level,
            "home_type": self.home_type,
            "experience_level": self.experience_level,
            "has_kids": self.has_kids,
            "has_other_pets": self.has_other_pets,
        }


class ChatbotLog(db.Model):
    """Every question put to the FAQ bot, with what the classifier made of it.

    Doubles as an evaluation set: the questions people actually ask, together
    with low-confidence rows, show exactly which intents need more training
    phrasings.
    """

    __tablename__ = "chatbot_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    question = db.Column(db.Text, nullable=False)
    predicted_intent = db.Column(db.String(40), nullable=False, index=True)
    confidence = db.Column(db.Float, nullable=False)
    low_confidence = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    user = db.relationship("User")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "question": self.question,
            "predicted_intent": self.predicted_intent,
            "confidence": round(self.confidence, 3),
            "low_confidence": self.low_confidence,
            "user": self.user.name if self.user else "Guest",
            "created_at": iso_utc(self.created_at),
        }


class RevokedToken(db.Model):
    """Tokens that have been logged out.

    Session cookies are cleared server-side by definition; a JWT is not, because
    the server keeps no session to clear. Without this table `/api/auth/logout`
    could only ask the browser to forget the token, and a copy of it would keep
    working until it expired. Rows are pruned once past `expires_at`.
    """

    __tablename__ = "revoked_tokens"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(36), unique=True, nullable=False, index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    revoked_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class Volunteer(db.Model):
    """A volunteer sign-up. Migrated from the old standalone Node/MongoDB
    service so the whole app runs off one SQLite database."""

    __tablename__ = "volunteers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, index=True)
    mobile = db.Column(db.String(32), nullable=False)
    address = db.Column(db.Text, nullable=False)
    state = db.Column(db.String(80), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    submitted_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "mobile": self.mobile,
            "address": self.address,
            "state": self.state,
            "city": self.city,
            "submitted_at": iso_utc(self.submitted_at),
        }


class MatchRequest(db.Model):
    """Audit row written on every /api/recommend call — this is what powers the
    activity numbers on the admin dashboard."""

    __tablename__ = "match_requests"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    adopter_id = db.Column(db.Integer, db.ForeignKey("adopters.id"), nullable=False)
    top_dog_id = db.Column(db.Integer, db.ForeignKey("dogs.id"), nullable=True)
    top_score = db.Column(db.Float, nullable=True)
    results_count = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)

    user = db.relationship("User", back_populates="match_requests")
    adopter = db.relationship("Adopter", back_populates="match_requests")
    top_dog = db.relationship("Dog")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": iso_utc(self.created_at),
            "user": self.user.name if self.user else "Guest",
            "adopter": self.adopter.to_dict() if self.adopter else None,
            "top_dog": self.top_dog.name if self.top_dog else None,
            "top_score": round(self.top_score, 1) if self.top_score is not None else None,
            "results_count": self.results_count,
        }


# --------------------------------------------------------------------------- #
# Medical records
#
# Five tables, each owned by one dog. Statuses are plain strings checked
# against the sets below, the same pattern as the questionnaire answers in
# app.py; the CHECK constraints repeat the rule in the database so a row
# written outside the API cannot hold a value the API would reject.
#
# Dates that are calendar days (a visit, a due date) are DATE; only the audit
# timestamps are DATETIME. `recorded_by_id` keeps who entered each row, and is
# set to NULL rather than blocking if that account is ever removed.
# --------------------------------------------------------------------------- #

MEDICAL_RECORD_TYPES = frozenset(
    {"checkup", "treatment", "surgery", "diagnostic", "emergency", "dental", "other"}
)
VACCINATION_STATUSES = frozenset({"scheduled", "completed", "overdue"})
MEDICATION_STATUSES = frozenset({"active", "completed", "discontinued"})
FOLLOW_UP_STATUSES = frozenset({"pending", "completed", "missed", "cancelled"})

# Accepted body temperature, in °C. A plausibility bound on the reading, not a
# clinical range: it rejects typos (389, or a Fahrenheit value) while still
# letting a genuinely hypo- or hyperthermic reading be recorded.
TEMPERATURE_RANGE_C = (30.0, 45.0)
MAX_WEIGHT_KG = 120.0  # above the heaviest breeds


def _in(column: str, values: frozenset) -> str:
    """SQL for a CHECK that `column` is one of `values`."""
    return f"{column} IN ({', '.join(repr(v) for v in sorted(values))})"


def _day(value) -> str | None:
    return value.isoformat() if value else None


def _dog_fk():
    return db.Column(
        db.Integer, db.ForeignKey("dogs.id", ondelete="CASCADE"), nullable=False, index=True
    )


def _recorded_by_fk():
    return db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class MedicalRecord(db.Model):
    """A vet visit, treatment or other clinical event."""

    __tablename__ = "medical_records"
    __table_args__ = (
        db.CheckConstraint(
            _in("record_type", MEDICAL_RECORD_TYPES), name="ck_medical_records_record_type"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    dog_id = _dog_fk()
    record_type = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=True)
    veterinarian = db.Column(db.String(120), nullable=True)
    visit_date = db.Column(db.Date, nullable=False, index=True)
    recorded_by_id = _recorded_by_fk()
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    dog = db.relationship("Dog", back_populates="medical_records")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dog_id": self.dog_id,
            "record_type": self.record_type,
            "title": self.title,
            "description": self.description,
            "veterinarian": self.veterinarian,
            "visit_date": _day(self.visit_date),
            "created_at": iso_utc(self.created_at),
            "updated_at": iso_utc(self.updated_at),
        }


class Vaccination(db.Model):
    __tablename__ = "vaccinations"
    __table_args__ = (
        db.CheckConstraint(_in("status", VACCINATION_STATUSES), name="ck_vaccinations_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    dog_id = _dog_fk()
    vaccine_name = db.Column(db.String(120), nullable=False)
    # NULL while only scheduled: a vaccine that has not been given has no date.
    administered_date = db.Column(db.Date, nullable=True)
    next_due_date = db.Column(db.Date, nullable=True, index=True)
    status = db.Column(db.String(20), nullable=False)
    veterinarian = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    recorded_by_id = _recorded_by_fk()
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    dog = db.relationship("Dog", back_populates="vaccinations")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dog_id": self.dog_id,
            "vaccine_name": self.vaccine_name,
            "administered_date": _day(self.administered_date),
            "next_due_date": _day(self.next_due_date),
            "status": self.status,
            "veterinarian": self.veterinarian,
            "notes": self.notes,
            "created_at": iso_utc(self.created_at),
            "updated_at": iso_utc(self.updated_at),
        }


class Medication(db.Model):
    __tablename__ = "medications"
    __table_args__ = (
        db.CheckConstraint(_in("status", MEDICATION_STATUSES), name="ck_medications_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    dog_id = _dog_fk()
    medication_name = db.Column(db.String(120), nullable=False)
    dosage = db.Column(db.String(80), nullable=False)
    frequency = db.Column(db.String(80), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=True)  # NULL = ongoing
    status = db.Column(db.String(20), nullable=False, index=True)
    prescribed_by = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    recorded_by_id = _recorded_by_fk()
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    dog = db.relationship("Dog", back_populates="medications")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dog_id": self.dog_id,
            "medication_name": self.medication_name,
            "dosage": self.dosage,
            "frequency": self.frequency,
            "start_date": _day(self.start_date),
            "end_date": _day(self.end_date),
            "status": self.status,
            "prescribed_by": self.prescribed_by,
            "notes": self.notes,
            "created_at": iso_utc(self.created_at),
            "updated_at": iso_utc(self.updated_at),
        }


class HealthObservation(db.Model):
    """One set of measurements on one day. Every measurement is optional, but
    the API requires at least one; weight and temperature are the series the
    later trend checks will read."""

    __tablename__ = "health_observations"
    __table_args__ = (
        db.CheckConstraint(
            f"weight_kg IS NULL OR (weight_kg > 0 AND weight_kg <= {MAX_WEIGHT_KG})",
            name="ck_health_observations_weight_kg",
        ),
        db.CheckConstraint(
            "temperature_c IS NULL OR (temperature_c >= {} AND temperature_c <= {})".format(
                *TEMPERATURE_RANGE_C
            ),
            name="ck_health_observations_temperature_c",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    dog_id = _dog_fk()
    observation_date = db.Column(db.Date, nullable=False, index=True)
    weight_kg = db.Column(db.Float, nullable=True)
    temperature_c = db.Column(db.Float, nullable=True)
    # A list of short strings rather than free text, so later phases can count
    # and compare symptoms without parsing prose.
    symptoms = db.Column(db.JSON, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    recorded_by_id = _recorded_by_fk()
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    # Observations can be corrected (a mistyped weight would skew any trend),
    # so they carry an updated_at like the other medical tables.
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    dog = db.relationship("Dog", back_populates="health_observations")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dog_id": self.dog_id,
            "observation_date": _day(self.observation_date),
            "weight_kg": self.weight_kg,
            "temperature_c": self.temperature_c,
            "symptoms": self.symptoms or [],
            "notes": self.notes,
            "created_at": iso_utc(self.created_at),
            "updated_at": iso_utc(self.updated_at),
        }


class FollowUp(db.Model):
    __tablename__ = "follow_ups"
    __table_args__ = (
        db.CheckConstraint(_in("status", FOLLOW_UP_STATUSES), name="ck_follow_ups_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    dog_id = _dog_fk()
    reason = db.Column(db.String(200), nullable=False)
    due_date = db.Column(db.Date, nullable=False, index=True)
    completed_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), nullable=False, index=True)
    notes = db.Column(db.Text, nullable=True)
    recorded_by_id = _recorded_by_fk()
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    dog = db.relationship("Dog", back_populates="follow_ups")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dog_id": self.dog_id,
            "reason": self.reason,
            "due_date": _day(self.due_date),
            "completed_date": _day(self.completed_date),
            "status": self.status,
            "notes": self.notes,
            "created_at": iso_utc(self.created_at),
            "updated_at": iso_utc(self.updated_at),
        }


# --------------------------------------------------------------------------- #
# Health alerts and notifications
#
# An alert is a health_intelligence finding that has been written down so it
# can be worked on: reviewed, acknowledged and resolved. The rules that produce
# findings stay in health_intelligence.py — nothing here re-decides severity or
# re-scores anything.
# --------------------------------------------------------------------------- #

ALERT_STATUSES = frozenset({"open", "acknowledged", "resolved"})
ALERT_SEVERITIES = frozenset({"low", "moderate", "high", "critical"})
ALERT_ACTIVE_STATUSES = ("open", "acknowledged")

NOTIFICATION_STATUSES = frozenset({"pending", "sent", "failed"})


class HealthAlert(db.Model):
    """One logical finding for one dog, tracked until it is resolved.

    Identity is (dog_id, finding_code, entity_key) — the partial unique index
    below allows only one *active* row per identity, which is what stops a
    repeated sync piling up duplicates. Resolved rows are history and are never
    reused: if the same finding comes back, a new row is created pointing at
    the old one through `reopened_from_id`.
    """

    __tablename__ = "health_alerts"
    __table_args__ = (
        db.CheckConstraint(_in("status", ALERT_STATUSES), name="ck_health_alerts_status"),
        db.CheckConstraint(_in("severity", ALERT_SEVERITIES), name="ck_health_alerts_severity"),
        # At most one open/acknowledged alert per logical finding. Partial, so
        # any number of resolved rows may sit behind it as history. Written for
        # both engines; SQLite and PostgreSQL both support partial indexes.
        db.Index(
            "uq_health_alerts_active_identity",
            "dog_id", "finding_code", "entity_key",
            unique=True,
            sqlite_where=db.text("status != 'resolved'"),
            postgresql_where=db.text("status != 'resolved'"),
        ),
        db.Index("ix_health_alerts_status_severity", "status", "severity"),
    )

    id = db.Column(db.Integer, primary_key=True)
    dog_id = _dog_fk()

    # --- what was found (copied from the Phase 4 finding, never recomputed) --
    category = db.Column(db.String(40), nullable=False)
    finding_code = db.Column(db.String(80), nullable=False, index=True)
    # The record the finding points at, as "<field>:<id>" (e.g. "follow_up_id:7"),
    # or "" for findings about a series rather than one row, such as a weight
    # trend. Part of the identity, so two overdue follow-ups stay two alerts.
    entity_key = db.Column(db.String(60), nullable=False, default="")
    severity = db.Column(db.String(20), nullable=False, index=True)
    title = db.Column(db.String(200), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    evidence = db.Column(db.JSON, nullable=True)
    recommendation = db.Column(db.Text, nullable=True)

    # The dog's overall score when this alert was first raised. Never updated:
    # it is the record of what the picture looked like at the time.
    risk_score_at_detection = db.Column(db.Integer, nullable=False)

    # --- lifecycle ---
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    first_detected_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    last_detected_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    detection_count = db.Column(db.Integer, nullable=False, default=1)

    acknowledged_at = db.Column(db.DateTime, nullable=True)
    acknowledged_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolution_note = db.Column(db.Text, nullable=True)
    # True when the sync closed it because the finding was gone, rather than a
    # person resolving it.
    auto_resolved = db.Column(db.Boolean, nullable=False, default=False)

    # The resolved alert this one recurred from, if any.
    reopened_from_id = db.Column(
        db.Integer, db.ForeignKey("health_alerts.id", ondelete="SET NULL"), nullable=True
    )

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    dog = db.relationship("Dog", back_populates="health_alerts")
    acknowledged_by = db.relationship("User", foreign_keys=[acknowledged_by_id])
    resolved_by = db.relationship("User", foreign_keys=[resolved_by_id])

    @property
    def is_active(self) -> bool:
        return self.status in ALERT_ACTIVE_STATUSES

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "dog_id": self.dog_id,
            "dog_name": self.dog.name if self.dog else None,
            "category": self.category,
            "finding_code": self.finding_code,
            "entity_key": self.entity_key or None,
            "severity": self.severity,
            "title": self.title,
            "reason": self.reason,
            "evidence": self.evidence or {},
            "recommendation": self.recommendation,
            "risk_score_at_detection": self.risk_score_at_detection,
            "status": self.status,
            "first_detected_at": iso_utc(self.first_detected_at),
            "last_detected_at": iso_utc(self.last_detected_at),
            "detection_count": self.detection_count,
            "acknowledged_at": iso_utc(self.acknowledged_at) if self.acknowledged_at else None,
            "acknowledged_by": self.acknowledged_by.name if self.acknowledged_by else None,
            "acknowledged_by_id": self.acknowledged_by_id,
            "resolved_at": iso_utc(self.resolved_at) if self.resolved_at else None,
            "resolved_by": self.resolved_by.name if self.resolved_by else None,
            "resolved_by_id": self.resolved_by_id,
            "resolution_note": self.resolution_note,
            "auto_resolved": self.auto_resolved,
            "reopened_from_id": self.reopened_from_id,
            "created_at": iso_utc(self.created_at),
            "updated_at": iso_utc(self.updated_at),
        }


class Notification(db.Model):
    """An outbox row. Nothing sends anything yet.

    Writing the event down and delivering it are deliberately separate: this
    phase only records that something happened, so adding email or SMS later
    means writing a sender that reads pending rows, with no change here.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        db.CheckConstraint(_in("status", NOTIFICATION_STATUSES), name="ck_notifications_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(40), nullable=False, index=True)
    dog_id = db.Column(
        db.Integer, db.ForeignKey("dogs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    alert_id = db.Column(
        db.Integer, db.ForeignKey("health_alerts.id", ondelete="CASCADE"), nullable=True
    )
    severity = db.Column(db.String(20), nullable=True)
    payload = db.Column(db.JSON, nullable=True)
    # "pending" for every row this phase writes: there is no sender.
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    channel = db.Column(db.String(20), nullable=False, default="internal")
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    delivered_at = db.Column(db.DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type,
            "dog_id": self.dog_id,
            "alert_id": self.alert_id,
            "severity": self.severity,
            "payload": self.payload or {},
            "status": self.status,
            "channel": self.channel,
            "created_at": iso_utc(self.created_at),
            "delivered_at": iso_utc(self.delivered_at) if self.delivered_at else None,
        }
