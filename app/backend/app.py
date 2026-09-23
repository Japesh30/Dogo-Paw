"""Dogo-Paw Flask API.

    python app.py           # dev server on http://127.0.0.1:5000
"""

from __future__ import annotations

import os
import re
import secrets
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from flask_migrate import Migrate
from sqlalchemy import func
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import check_password_hash, generate_password_hash

from auth import (
    admin_required,
    bearer_token,
    decode_token,
    issue_token,
    load_user,
    login_required,
    revoke,
)
import medical
from ml import chatbot, health_anomaly_service, segmentation, success_model
from models import (
    Adopter,
    ChatbotLog,
    Dog,
    MatchRequest,
    User,
    Volunteer,
    db,
    iso_utc,
)
from ratelimit import rate_limit
from recommender import AdopterProfile, DogProfile, recommend

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Which environment this process is running as. Everything that must not be
# permissive on the public internet keys off this one flag, so there is a
# single place to look when asking "is this safe to expose?".
APP_ENV = os.environ.get("APP_ENV", "development").strip().lower()
IS_PRODUCTION = APP_ENV == "production"

# Origins the dev frontend runs on. Production never falls back to these.
DEV_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

# Nothing this API accepts is large — the biggest legitimate body is a
# volunteer form at well under 1 KB. Rejecting anything bigger before it is
# parsed stops a large body being read into memory at all.
MAX_CONTENT_LENGTH = 64 * 1024  # 64 KB

# Upper bounds on free-text fields, so a valid-looking value cannot be
# unbounded. Chosen to sit above any realistic real-world input.
MAX_NAME = 120
MAX_EMAIL = 255
MAX_PASSWORD = 128  # werkzeug hashes anything, but an unbounded password is
                    # free CPU for an attacker
MIN_PASSWORD = 6
MAX_QUESTION = 500  # the chat box; unchanged, just named

# These three mirror the volunteers table's column widths exactly. PostgreSQL
# enforces a VARCHAR length, SQLite does not, so they have to be checked in the
# application for the two to behave the same.
MAX_MOBILE = 32   # volunteers.mobile VARCHAR(32)
MAX_REGION = 80   # volunteers.state / .city VARCHAR(80)
MAX_ADDRESS = 500

# Rate limits: (requests, seconds). Documented in docs/SECURITY.md.
LIMITS = {
    "login": (10, 15 * 60),      # 10 per 15 min — stops online password guessing
    "register": (5, 60 * 60),    # 5 per hour — stops bulk account creation
    "chatbot": (20, 60),         # 20 per min — each call writes a ChatbotLog row
    "recommend": (10, 60),       # 10 per min — each call writes a MatchRequest row
    "volunteer": (5, 60 * 60),   # 5 per hour — writes PII; a human submits once
}

# Trained artifacts warmed at startup so no request ever pays for a load.
MODEL_LOADERS = [
    ("success predictor", success_model.load_model),
    ("intent classifier", chatbot.load_model),
    # Warmed here too, so the first health analysis does not pay the load and a
    # missing or stale artifact shows up in the boot log rather than silently at
    # the first request.
    ("health anomaly detector", health_anomaly_service.load_model),
]

# Accepted questionnaire answers, mirrored by the React form.
VALID = {
    "activity_level": {"low", "medium", "high"},
    "home_type": {"apartment", "house_no_yard", "house_with_yard"},
    "experience_level": {"none", "some", "experienced"},
}


def resolve_secret_key() -> str:
    """SECRET_KEY from the environment if set; otherwise, in development only, a
    random one generated once and cached in `.secret_key` (gitignored).

    A hardcoded fallback would mean every copy of this repo shares a signing
    key, so anyone could mint a valid admin token. Generating on first run keeps
    local startup zero-config without that.

    In production the generated-file path is refused outright. A hosted
    filesystem is ephemeral, so the key would silently change on every restart,
    invalidating every issued token and signing all users out — and two
    instances would not accept each other's tokens. Failing loudly at startup is
    far better than that failing quietly at runtime.
    """
    from_env = os.environ.get("SECRET_KEY", "").strip()
    if from_env:
        if IS_PRODUCTION and len(from_env) < 32:
            raise RuntimeError(
                "SECRET_KEY is too short for production (need at least 32 "
                "characters). Generate one with: python -c \"import secrets; "
                "print(secrets.token_hex(32))\""
            )
        return from_env

    if IS_PRODUCTION:
        raise RuntimeError(
            "SECRET_KEY must be set when APP_ENV=production. Generate one with: "
            "python -c \"import secrets; print(secrets.token_hex(32))\""
        )

    key_file = BASE_DIR / ".secret_key"
    if key_file.exists():
        return key_file.read_text(encoding="utf-8").strip()

    key = secrets.token_hex(32)
    key_file.write_text(key, encoding="utf-8")
    print(f"generated a new development signing key -> {key_file.name}")
    return key


def resolve_database_uri() -> str:
    """DATABASE_URL, normalised to something SQLAlchemy 2 will actually accept.

    Two rewrites, both needed for a hosted Postgres:

    * `postgres://` -> `postgresql://`. Supabase, Render and Heroku all hand out
      the shorter form; SQLAlchemy 2 dropped it and raises "Can't load plugin"
      rather than guessing.
    * `postgresql://` -> `postgresql+psycopg://`. Without an explicit driver,
      SQLAlchemy reaches for psycopg2, which is not installed — this project
      uses psycopg 3. Naming the driver is what makes the dependency honest.

    Anything already carrying a `+driver` is left alone, so someone who
    deliberately wants psycopg2 or asyncpg is not overridden. A missing
    DATABASE_URL falls back to the local SQLite file, which is what keeps
    development zero-config.
    """
    raw = os.environ.get("DATABASE_URL", "").strip()
    if not raw:
        return f"sqlite:///{BASE_DIR / 'dogopaw.db'}"

    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://"):]

    if raw.startswith("postgresql://"):
        raw = "postgresql+psycopg://" + raw[len("postgresql://"):]

    return raw


def engine_options(uri: str) -> dict:
    """Connection-pool settings, only where they earn their place.

    SQLite is a local file and needs none of this. A hosted Postgres does:
    Supabase's pooler closes idle connections and a free Render instance sleeps,
    so a pooled connection is routinely dead by the time the next request
    borrows it.

    * `pool_pre_ping` sends a cheap SELECT 1 before handing a connection out and
      transparently replaces it if the check fails. Without it, the first
      request after an idle period fails instead of reconnecting — which during
      a demo looks exactly like a broken site.
    * `pool_recycle` retires connections before the pooler's own idle timeout
      can, so the pre-ping rarely has to do the work.
    """
    if not uri.startswith("postgresql"):
        return {}

    return {
        "pool_pre_ping": True,
        "pool_recycle": 280,  # under Supabase's ~300s idle cutoff
        "pool_size": 5,
        "max_overflow": 2,
        # Named so a hung query shows up as this app in Supabase's dashboard
        # rather than an anonymous connection.
        "connect_args": {"application_name": "dogo-paw-api"},
    }


def resolve_cors_origins() -> list[str]:
    """The exact origins allowed to call this API from a browser.

    `*` is refused in production: with a wildcard, any site a visitor happens to
    be on can call this API with their browser. Development falls back to the
    two localhost origins Vite serves on, so local work stays zero-config.
    """
    raw = os.environ.get("CORS_ORIGINS", "").strip()

    if raw == "*":
        if IS_PRODUCTION:
            raise RuntimeError(
                "CORS_ORIGINS='*' is not allowed when APP_ENV=production. "
                "Set it to your frontend origin, e.g. "
                "CORS_ORIGINS=https://dogo-paw.vercel.app"
            )
        return ["*"]

    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if origins:
        return origins

    if IS_PRODUCTION:
        raise RuntimeError(
            "CORS_ORIGINS must be set when APP_ENV=production, e.g. "
            "CORS_ORIGINS=https://dogo-paw.vercel.app"
        )
    return DEV_CORS_ORIGINS


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = resolve_secret_key()
    database_uri = resolve_database_uri()
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options(database_uri)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
    app.config["APP_ENV"] = APP_ENV

    # Debug can never be on in production, whatever the environment says. The
    # Werkzeug debugger offers an interactive console to anyone who can trigger
    # an exception, which is remote code execution on a public host.
    app.config["DEBUG"] = False
    app.config["TESTING"] = False
    # Without this, an unhandled error would re-raise and render a traceback.
    app.config["PROPAGATE_EXCEPTIONS"] = False

    # Off in tests only; on everywhere else, including development, so the
    # limits are exercised in the same place they are written.
    app.config["RATE_LIMIT_ENABLED"] = (
        os.environ.get("RATE_LIMIT_ENABLED", "true").strip().lower()
        not in {"false", "0", "no"}
    )

    if IS_PRODUCTION:
        # Behind Render's proxy, request.remote_addr is the proxy. ProxyFix
        # rewrites it from the first hop of X-Forwarded-For, which is what the
        # rate limiter keys on — without it every visitor shares one address and
        # one abuser locks out everybody.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    # render_as_batch: SQLite cannot ALTER most things in place, so generated
    # migrations copy-and-swap the table there; PostgreSQL ignores it.
    Migrate(app, db, directory=str(BASE_DIR / "migrations"), render_as_batch=True)
    CORS(
        app,
        resources={r"/api/*": {"origins": resolve_cors_origins()}},
        # The API authenticates with a bearer token, never a cookie, so the
        # browser is never asked to attach credentials cross-origin.
        supports_credentials=False,
    )
    app.before_request(load_user)
    register_routes(app)
    app.register_blueprint(medical.bp)
    app.register_blueprint(medical.admin_bp)
    register_error_handlers(app)

    # The backend name only. DATABASE_URL carries the database password, so it
    # must never reach a log line.
    print(f"database: {database_uri.split('://', 1)[0]} ({APP_ENV})")

    # Startup migrates and seeds by default, which is what keeps a Render deploy
    # a single step. DB_AUTO_MIGRATE=false turns that off, so `flask db current`
    # or `flask db upgrade --sql` can inspect a database without this process
    # changing it first.
    if os.environ.get("DB_AUTO_MIGRATE", "true").strip().lower() in {"false", "0", "no"}:
        print("DB_AUTO_MIGRATE is off: skipping startup migration and seed")
    else:
        with app.app_context():
            from seed import seed

            seed()

    # Load the trained models once, at startup — never on a request. A missing
    # artifact is a warning, not a crash: the site still works without the
    # optional ML extras, it just stops offering them.
    for label, loader in MODEL_LOADERS:
        try:
            loader()
            print(f"loaded {label}")
        except Exception as exc:
            # Every model here is an optional extra: a missing or unreadable
            # artifact degrades one feature and must never stop the site from
            # booting. The feature reports itself unavailable at request time.
            print(f"WARNING: {label} unavailable — {exc}")

    return app


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def payload() -> dict:
    return request.get_json(silent=True) or {}


def error(message: str, status: int = 400):
    return jsonify({"error": message}), status


def text(data: dict, key: str) -> str:
    """A trimmed string field, or "" if it is missing or not a string.

    JSON lets a client send `{"name": {"$ne": null}}` or `{"name": 12}` just as
    easily as a string. Calling .strip() on those raised AttributeError and came
    back as a 500; funnelling every field through here turns a wrong type into
    an ordinary "this is required" 400 instead.
    """
    value = data.get(key)
    return value.strip() if isinstance(value, str) else ""


def too_long(value: str, limit: int, label: str):
    """A 400 if `value` is over `limit`, otherwise None."""
    return error(f"{label} is too long (max {limit} characters).") if len(value) > limit else None


def as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "y"}
    return bool(value)


def register_routes(app: Flask) -> None:
    # ----------------------------------------------------------------- auth #
    @app.post("/api/auth/register")
    @rate_limit("register", *LIMITS["register"])
    def register():
        data = payload()
        name = text(data, "name")
        email = text(data, "email").lower()
        password = data.get("password")
        password = password if isinstance(password, str) else ""

        if not name:
            return error("Please enter your name.")
        if (err := too_long(name, MAX_NAME, "Name")):
            return err
        if len(email) > MAX_EMAIL or not EMAIL_RE.match(email):
            return error("Please enter a valid email address.")
        if len(password) < MIN_PASSWORD:
            return error(f"Password must be at least {MIN_PASSWORD} characters.")
        if (err := too_long(password, MAX_PASSWORD, "Password")):
            return err
        if User.query.filter_by(email=email).first():
            return error("An account with that email already exists.", 409)

        user = User(
            name=name,
            email=email,
            password_hash=generate_password_hash(password),
        )
        db.session.add(user)
        db.session.commit()

        return jsonify({"token": issue_token(user), "user": user.to_dict()}), 201

    @app.post("/api/auth/login")
    @rate_limit("login", *LIMITS["login"])
    def login():
        data = payload()
        email = text(data, "email").lower()
        password = data.get("password")
        password = password if isinstance(password, str) else ""

        # Bail before hashing on anything that cannot be a stored credential, so
        # an oversized body is never turned into work.
        if len(email) > MAX_EMAIL or len(password) > MAX_PASSWORD:
            return error("Email or password is incorrect.", 401)

        user = User.query.filter_by(email=email).first()
        if user is None or not check_password_hash(user.password_hash, password):
            return error("Email or password is incorrect.", 401)

        return jsonify({"token": issue_token(user), "user": user.to_dict()})

    @app.get("/api/auth/me")
    @login_required
    def me():
        return jsonify({"user": g.current_user.to_dict()})

    @app.post("/api/auth/logout")
    def logout():
        """Revoke the caller's token server-side, so a copy of it is dead even
        if the browser kept one. Safe to call twice."""
        raw = bearer_token()
        payload = decode_token(raw) if raw else None
        revoked = revoke(payload) if payload else False
        return jsonify({"message": "Logged out.", "revoked": revoked})

    # ----------------------------------------------------------------- dogs #
    @app.get("/api/dogs")
    def list_dogs():
        """Every dog, full profile included.

        The gallery filters client-side against this one payload rather than
        asking the server for each combination — 18 rows is nothing to send, and
        it makes filtering instant with no request per keystroke.
        """
        dogs = Dog.query.order_by(Dog.id).all()
        return jsonify({"count": len(dogs), "dogs": [d.to_dict() for d in dogs]})

    @app.get("/api/dogs/<int:dog_id>")
    def get_dog(dog_id: int):
        dog = db.session.get(Dog, dog_id)
        if dog is None:
            return error(f"No dog with id {dog_id}.", 404)
        return jsonify({"dog": dog.to_dict()})

    # ----------------------------------------------------------- volunteer #
    @app.post("/api/volunteer")
    @rate_limit("volunteer", *LIMITS["volunteer"])
    def volunteer_signup():
        """Never trust the client's validation — every rule the React form
        enforces is re-checked here."""
        data = payload()

        fields = {
            key: text(data, key)
            for key in ("name", "email", "mobile", "address", "state", "city")
        }

        labels = {
            "name": "Name",
            "email": "Email",
            "mobile": "Mobile",
            "address": "Address",
            "state": "State",
            "city": "City",
        }
        for key, label in labels.items():
            if not fields[key]:
                return error(f"{label} is required.")

        if not EMAIL_RE.match(fields["email"]):
            return error("Please enter a valid email address.")

        digits = re.sub(r"\D", "", fields["mobile"])
        if len(digits) < 10:
            return error("Mobile number must have at least 10 digits.")
        if len(digits) > 15:
            return error("Mobile number looks too long.")

        # Every cap below matches the column it is written to. SQLite ignores a
        # VARCHAR length and stores an over-long value silently; PostgreSQL
        # raises, which would turn a bad form post into a 500. Validating here
        # means the same input is rejected the same way on both.
        for key, limit in (
            ("name", MAX_NAME),        # users.name        VARCHAR(120)
            ("email", MAX_EMAIL),      # volunteers.email  VARCHAR(255)
            ("mobile", MAX_MOBILE),    # volunteers.mobile VARCHAR(32)
            ("state", MAX_REGION),     # volunteers.state  VARCHAR(80)
            ("city", MAX_REGION),      # volunteers.city   VARCHAR(80)
            ("address", MAX_ADDRESS),  # volunteers.address TEXT
        ):
            if (err := too_long(fields[key], limit, labels[key])):
                return err

        volunteer = Volunteer(
            name=fields["name"],
            email=fields["email"].lower(),
            mobile=fields["mobile"],
            address=fields["address"],
            state=fields["state"],
            city=fields["city"],
        )
        db.session.add(volunteer)
        db.session.commit()

        # Message text matches what the migrated form already expects.
        return jsonify(
            {"message": "Volunteer request recorded!", "volunteer": volunteer.to_dict()}
        ), 201

    # ------------------------------------------------------------ recommend #
    @app.post("/api/recommend")
    @rate_limit("recommend", *LIMITS["recommend"])
    def recommend_dogs():
        data = payload()

        for field, allowed in VALID.items():
            value = text(data, field).lower()
            if value not in allowed:
                return error(
                    f"'{field}' must be one of: {', '.join(sorted(allowed))}."
                )

        adopter_row = Adopter(
            user_id=g.current_user.id if g.current_user else None,
            activity_level=data["activity_level"].strip().lower(),
            home_type=data["home_type"].strip().lower(),
            experience_level=data["experience_level"].strip().lower(),
            has_kids=as_bool(data.get("has_kids")),
            has_other_pets=as_bool(data.get("has_other_pets")),
        )
        db.session.add(adopter_row)
        db.session.flush()  # need adopter_row.id for the audit row below

        profile = AdopterProfile(
            activity_level=adopter_row.activity_level,
            home_type=adopter_row.home_type,
            experience_level=adopter_row.experience_level,
            has_kids=adopter_row.has_kids,
            has_other_pets=adopter_row.has_other_pets,
        )

        dogs = [
            DogProfile(
                dog_id=d.id,
                name=d.name,
                age=d.age,
                energy_level=d.energy_level,
                size=d.size,
                temperament=d.temperament,
                medical_needs=d.medical_needs,
                good_with_kids=d.good_with_kids,
                good_with_other_pets=d.good_with_other_pets,
                photo_url=d.photo_url,
            )
            for d in Dog.query.order_by(Dog.id).all()
        ]

        results = recommend(dogs, profile)

        # Score every dog for predicted adoption success in one matrix op,
        # rather than making the results page call /api/predict-success 18
        # times. Optional: if the model artifact is missing the page still
        # renders, just without the second number.
        try:
            probabilities = success_model.predict_success_batch(
                adopter_row.to_dict(),
                [
                    {
                        "energy_level": r.dog.energy_level,
                        "size": r.dog.size,
                        "temperament": r.dog.temperament,
                        "medical_needs": r.dog.medical_needs,
                        "good_with_kids": r.dog.good_with_kids,
                        "good_with_other_pets": r.dog.good_with_other_pets,
                    }
                    for r in results
                ],
            )
        except FileNotFoundError:
            probabilities = [None] * len(results)

        top = results[0] if results else None

        db.session.add(
            MatchRequest(
                user_id=adopter_row.user_id,
                adopter_id=adopter_row.id,
                top_dog_id=top.dog.dog_id if top else None,
                top_score=top.score if top else None,
                results_count=len(results),
            )
        )
        db.session.commit()

        matches = []
        for result, probability in zip(results, probabilities):
            payload_row = result.to_dict()
            payload_row["success_probability"] = probability
            matches.append(payload_row)

        return jsonify(
            {
                "adopter": adopter_row.to_dict(),
                "count": len(results),
                "matches": matches,
            }
        )

    # -------------------------------------------------------------- chatbot #
    @app.post("/api/chatbot")
    @rate_limit("chatbot", *LIMITS["chatbot"])
    def chatbot_reply():
        data = payload()
        message = text(data, "message")

        if not message:
            return error("Please type a question.")
        if len(message) > MAX_QUESTION:
            return error("That question is a bit long — try shortening it.")

        try:
            result = chatbot.classify(message)
        except FileNotFoundError:
            return error("The chatbot model has not been trained yet.", 503)

        db.session.add(
            ChatbotLog(
                user_id=g.current_user.id if g.current_user else None,
                question=message,
                predicted_intent=result["intent"],
                confidence=result["confidence"],
                low_confidence=result["low_confidence"],
            )
        )
        db.session.commit()

        return jsonify(result)

    # ------------------------------------------------- success prediction #
    @app.post("/api/predict-success")
    def predict_success():
        """Probability that one specific adopter-dog pairing lasts.

        Accepts the adopter profile plus either `dog_id` (looked up here) or a
        full inline dog object, so it is usable without hitting /api/dogs first.
        """
        data = payload()

        for field, allowed in VALID.items():
            if text(data, field).lower() not in allowed:
                return error(
                    f"'{field}' must be one of: {', '.join(sorted(allowed))}."
                )

        adopter = {
            "activity_level": data["activity_level"].strip().lower(),
            "home_type": data["home_type"].strip().lower(),
            "experience_level": data["experience_level"].strip().lower(),
            "has_kids": as_bool(data.get("has_kids")),
            "has_other_pets": as_bool(data.get("has_other_pets")),
        }

        if data.get("dog_id") is not None:
            # Coerce before it reaches the database. SQLite quietly returns no
            # row for a non-numeric id, but PostgreSQL raises, which would
            # surface as a 500 for what is really a bad request.
            try:
                dog_id = int(data["dog_id"])
            except (TypeError, ValueError):
                return error("'dog_id' must be a number.")
            dog_row = db.session.get(Dog, dog_id)
            if dog_row is None:
                return error(f"No dog with id {dog_id}.", 404)
            dog = dog_row.to_dict()
        elif isinstance(data.get("dog"), dict):
            dog = data["dog"]
            missing = [
                k
                for k in (
                    "energy_level", "size", "temperament",
                    "medical_needs", "good_with_kids", "good_with_other_pets",
                )
                if k not in dog
            ]
            if missing:
                return error(f"dog is missing: {', '.join(missing)}.")
        else:
            return error("Provide either 'dog_id' or a full 'dog' object.")

        try:
            probability = success_model.predict_success(adopter, dog)
        except FileNotFoundError:
            return error("The success model has not been trained yet.", 503)

        return jsonify(
            {
                "success_probability": probability,
                "adopter": adopter,
                "dog": {"name": dog.get("name"), "dog_id": dog.get("dog_id")},
                "model": "LogisticRegression",
            }
        )

    @app.get("/api/model-info")
    def model_info():
        """Training metrics and coefficients — powers the 'which factors
        predict success' slide, and lets the dashboard show them."""
        try:
            return jsonify(success_model.coefficient_report())
        except FileNotFoundError:
            return error("The success model has not been trained yet.", 503)

    # ---------------------------------------------------------------- admin #
    @app.get("/api/admin/stats")
    @admin_required
    def admin_stats():
        today = datetime.now(timezone.utc).date()
        window_start = today - timedelta(days=6)

        rows = (
            MatchRequest.query.filter(
                MatchRequest.created_at >= datetime.combine(window_start, datetime.min.time())
            )
            .order_by(MatchRequest.created_at)
            .all()
        )

        # Bucket by calendar day, filling gaps so the chart has 7 points.
        per_day = Counter(r.created_at.date() for r in rows)
        activity = [
            {
                "date": (day := window_start + timedelta(days=i)).isoformat(),
                "label": day.strftime("%a"),
                "requests": per_day.get(day, 0),
            }
            for i in range(7)
        ]

        recent = (
            MatchRequest.query.order_by(MatchRequest.created_at.desc()).limit(10).all()
        )

        # Volunteer sign-ups bucketed onto the same 7-day window as matches, so
        # the dashboard can show both streams against one axis.
        volunteer_rows = Volunteer.query.filter(
            Volunteer.submitted_at
            >= datetime.combine(window_start, datetime.min.time())
        ).all()
        volunteers_per_day = Counter(v.submitted_at.date() for v in volunteer_rows)
        for entry in activity:
            entry["volunteers"] = volunteers_per_day.get(
                date.fromisoformat(entry["date"]), 0
            )

        recent_volunteers = (
            Volunteer.query.order_by(Volunteer.submitted_at.desc()).limit(10).all()
        )

        # One combined feed: both event types, newest first.
        feed = [
            {
                "type": "match",
                "at": iso_utc(r.created_at),
                "who": r.user.name if r.user else "Guest",
                "detail": (
                    f"Top match {r.top_dog.name} at {round(r.top_score, 1)}%"
                    if r.top_dog
                    else "Ran the adoption matcher"
                ),
            }
            for r in recent
        ] + [
            {
                "type": "volunteer",
                "at": iso_utc(v.submitted_at),
                "who": v.name,
                "detail": f"Signed up to volunteer from {v.city}, {v.state}",
            }
            for v in recent_volunteers
        ]
        feed.sort(key=lambda e: e["at"], reverse=True)

        # Chatbot activity: which intents people ask about, plus the most recent
        # questions. Low-confidence rows are the ones worth reading — they show
        # where the classifier needs more training phrasings.
        intent_counts = (
            db.session.query(
                ChatbotLog.predicted_intent, func.count(ChatbotLog.id)
            )
            .group_by(ChatbotLog.predicted_intent)
            .order_by(func.count(ChatbotLog.id).desc())
            .all()
        )
        chatbot_activity = {
            "total": ChatbotLog.query.count(),
            "low_confidence": ChatbotLog.query.filter_by(low_confidence=True).count(),
            "by_intent": [
                {"intent": intent, "count": count} for intent, count in intent_counts
            ],
            "recent": [
                log.to_dict()
                for log in ChatbotLog.query.order_by(ChatbotLog.created_at.desc())
                .limit(8)
                .all()
            ],
        }

        top_dogs = (
            db.session.query(Dog.name, func.count(MatchRequest.id).label("wins"))
            .join(MatchRequest, MatchRequest.top_dog_id == Dog.id)
            .group_by(Dog.id)
            .order_by(func.count(MatchRequest.id).desc())
            .limit(5)
            .all()
        )

        avg_score = db.session.query(func.avg(MatchRequest.top_score)).scalar()

        return jsonify(
            {
                "totals": {
                    "dogs": Dog.query.count(),
                    "users": User.query.count(),
                    "adopters": Adopter.query.count(),
                    "volunteers": Volunteer.query.count(),
                    "match_requests": MatchRequest.query.count(),
                    "chatbot_questions": ChatbotLog.query.count(),
                    "avg_top_score": round(avg_score, 1) if avg_score else 0,
                },
                "activity": activity,
                "top_dogs": [{"name": n, "wins": w} for n, w in top_dogs],
                "recent_requests": [r.to_dict() for r in recent],
                "recent_activity": feed[:12],
                "chatbot": chatbot_activity,
            }
        )

    @app.get("/api/admin/adopter-segments")
    @admin_required
    def adopter_segments():
        """K-means personas over every adopter profile submitted so far.

        Clustered on request rather than cached: the dataset is small, and a
        stale segmentation would be worse than a 20 ms one.
        """
        rows = [a.to_dict() for a in Adopter.query.all()]
        return jsonify(segmentation.segment(rows))

    # --------------------------------------------------------------- health #
    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok", "time": datetime.now(timezone.utc).isoformat()})


def register_error_handlers(app: Flask) -> None:
    """Every error leaves as the same shape of JSON the client already expects:
    `{"error": "..."}`.

    The messages are written for a visitor, and deliberately say nothing about
    what went wrong internally. Flask's default 500 page and any SQLAlchemy
    exception text would otherwise carry table names, SQL, file paths and
    library versions into a public response.
    """

    @app.errorhandler(404)
    def not_found(_):
        return error("Not found.", 404)

    @app.errorhandler(405)
    def method_not_allowed(_):
        return error("That method is not allowed on this endpoint.", 405)

    @app.errorhandler(413)
    def payload_too_large(_):
        return error("That request body is too large.", 413)

    @app.errorhandler(429)
    def too_many_requests(_):
        return error("Too many requests. Please wait a moment and try again.", 429)

    @app.errorhandler(Exception)
    def internal_error(exc):
        # Let Flask handle its own HTTP errors (abort(...), routing) normally;
        # this branch is only for genuinely unexpected exceptions.
        from werkzeug.exceptions import HTTPException

        if isinstance(exc, HTTPException):
            return error(exc.description or "Request failed.", exc.code or 500)

        # A half-finished transaction must not be reused by the next request on
        # this connection.
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001 - never mask the original failure
            pass

        # The detail goes to the server log, where the operator can see it. The
        # caller gets nothing but the fact that it failed.
        app.logger.exception("unhandled error on %s %s", request.method, request.path)
        return error("Something went wrong on our end. Please try again.", 500)


app = create_app()

if __name__ == "__main__":
    # Development entry point only. In production the app is served by a WSGI
    # server importing `app` from this module, so this block never runs there.
    #
    # debug is tied to APP_ENV rather than written as a literal: the Werkzeug
    # debugger exposes an interactive Python console to anyone who can trigger
    # an exception, so it must not be reachable on a public host even if this
    # file is started by mistake.
    if IS_PRODUCTION:
        print(
            "APP_ENV=production - refusing to start the development server.\n"
            "Serve the app with a WSGI server instead, e.g.:\n"
            "    gunicorn app:app"
        )
        raise SystemExit(1)

    # 5001 rather than Flask's usual 5000, which is often already taken.
    app.run(debug=True, port=int(os.environ.get("PORT", 5001)))
