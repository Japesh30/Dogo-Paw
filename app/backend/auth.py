"""JWT issuing and the decorators that guard protected routes."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import current_app, g, jsonify, request

from models import RevokedToken, User, db, utcnow

TOKEN_TTL = timedelta(days=7)


def issue_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "is_admin": user.is_admin,
        # Unique id so this specific token can later be revoked on logout.
        "jti": uuid.uuid4().hex,
        "iat": now,
        "exp": now + TOKEN_TTL,
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def decode_token(raw: str) -> dict | None:
    try:
        return jwt.decode(
            raw, current_app.config["SECRET_KEY"], algorithms=["HS256"]
        )
    except jwt.PyJWTError:
        return None


def bearer_token() -> str | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    return header.removeprefix("Bearer ").strip()


def is_revoked(jti: str | None) -> bool:
    if not jti:
        return False
    return (
        db.session.query(RevokedToken.id).filter_by(jti=jti).first() is not None
    )


def revoke(payload: dict) -> bool:
    """Add a token's id to the denylist. Returns False if it was already there."""
    jti = payload.get("jti")
    if not jti or is_revoked(jti):
        return False

    db.session.add(
        RevokedToken(
            jti=jti,
            expires_at=datetime.fromtimestamp(payload["exp"], timezone.utc).replace(
                tzinfo=None
            ),
        )
    )
    # A revoked token is only worth remembering until it would have expired.
    RevokedToken.query.filter(RevokedToken.expires_at < utcnow()).delete()
    db.session.commit()
    return True


def _user_from_request() -> User | None:
    """Resolve the bearer token to a User, or None if absent/invalid/revoked."""
    raw = bearer_token()
    if raw is None:
        return None

    payload = decode_token(raw)
    if payload is None or is_revoked(payload.get("jti")):
        return None

    try:
        return db.session.get(User, int(payload["sub"]))
    except (KeyError, TypeError, ValueError):
        return None


def load_user() -> None:
    """before_request hook: attach the caller (or None) to flask.g."""
    g.current_user = _user_from_request()


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if getattr(g, "current_user", None) is None:
            return jsonify({"error": "Authentication required."}), 401
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = getattr(g, "current_user", None)
        if user is None:
            return jsonify({"error": "Authentication required."}), 401
        if not user.is_admin:
            return jsonify({"error": "Admin access required."}), 403
        return fn(*args, **kwargs)

    return wrapper
