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
