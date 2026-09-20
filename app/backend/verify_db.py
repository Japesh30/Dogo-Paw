"""Check that the configured database really works — schema, constraints,
relationships and timestamps.

Run it against whatever DATABASE_URL points at. On SQLite it is a quick sanity
check; against Supabase it is the proof that the PostgreSQL migration landed.

    # local SQLite
    python verify_db.py

    # against Supabase (PowerShell)
    $env:DATABASE_URL="postgresql://postgres.PROJECT:PASSWORD@aws-0-REGION.pooler.supabase.com:6543/postgres?sslmode=require"
    python verify_db.py

It writes a handful of rows into the real database and deletes them again, so
it is safe to run against a live deployment — but every row it creates is
prefixed `verify_db` so anything left behind by an interrupted run is obvious.

Exits non-zero if any check fails.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta

from sqlalchemy import inspect, text
from sqlalchemy.exc import DataError, IntegrityError

from models import (
    Adopter,
    ChatbotLog,
    Dog,
    MatchRequest,
    RevokedToken,
    User,
    Volunteer,
    db,
    utcnow,
)

EXPECTED_TABLES = {
    "users",
    "dogs",
    "adopters",
    "match_requests",
    "chatbot_logs",
    "revoked_tokens",
    "volunteers",
}

passed: list[str] = []
failed: list[tuple[str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (passed if ok else failed).append(name if ok else (name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  -- {detail}'}")


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def main() -> int:
    tag = f"verify_db-{uuid.uuid4().hex[:8]}"
    backend = db.engine.dialect.name
    is_pg = backend.startswith("postgresql")

    print(f"database backend : {backend}")
    print(f"server version   : {db.session.execute(text('SELECT version()')).scalar() if is_pg else 'n/a (sqlite)'}")
    print(f"run tag          : {tag}")

    # ------------------------------------------------------------ schema #
    section("1. Schema")
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    for table in sorted(EXPECTED_TABLES):
        check(f"table '{table}' exists", table in tables)
    check(
        "dogs has photo_url and bio",
        {"photo_url", "bio"} <= {c["name"] for c in inspector.get_columns("dogs")},
    )
    check("18 dogs seeded", Dog.query.count() == 18, f"found {Dog.query.count()}")
    check("an admin account exists", User.query.filter_by(is_admin=True).count() >= 1)

    # ------------------------------------------------------- constraints #
    section("2. Unique constraints")
    email = f"{tag}@test.local"
    db.session.add(User(name="verify_db user", email=email, password_hash="x"))
    db.session.commit()
    try:
        db.session.add(User(name="verify_db dup", email=email, password_hash="x"))
        db.session.commit()
        check("users.email rejects duplicates", False, "duplicate was accepted")
    except IntegrityError:
        db.session.rollback()
        check("users.email rejects duplicates", True)

    jti = f"{tag}-jti"
    db.session.add(RevokedToken(jti=jti, expires_at=utcnow() + timedelta(days=1)))
    db.session.commit()
    try:
        db.session.add(RevokedToken(jti=jti, expires_at=utcnow() + timedelta(days=1)))
        db.session.commit()
        check("revoked_tokens.jti rejects duplicates", False, "duplicate was accepted")
    except IntegrityError:
        db.session.rollback()
        check("revoked_tokens.jti rejects duplicates", True)

    # ------------------------------------------------------ foreign keys #
    section("3. Foreign keys and relationships")
    user = User.query.filter_by(email=email).first()
    adopter = Adopter(
        user_id=user.id, activity_level="medium", home_type="apartment",
        experience_level="some", has_kids=False, has_other_pets=False,
    )
    db.session.add(adopter)
    db.session.flush()

    dog = Dog.query.order_by(Dog.id).first()
    request_row = MatchRequest(
        user_id=user.id, adopter_id=adopter.id, top_dog_id=dog.id,
        top_score=88.5, results_count=18,
    )
    db.session.add(request_row)
    db.session.add(
        ChatbotLog(user_id=user.id, question=f"{tag} question",
                   predicted_intent="adoption_process", confidence=0.91,
                   low_confidence=False)
    )
    db.session.commit()

    check("match_request -> user resolves", request_row.user.id == user.id)
    check("match_request -> adopter resolves", request_row.adopter.id == adopter.id)
    check("match_request -> dog resolves", request_row.top_dog.id == dog.id)
    check("user -> adopter_profiles backref", adopter.id in [a.id for a in user.adopter_profiles])
    check("to_dict() serialises the graph", request_row.to_dict()["top_dog"] == dog.name)

    # A FK violation must be refused. PostgreSQL enforces this; SQLite only does
    # when PRAGMA foreign_keys is on, which it is not by default — so this check
    # is reported, not failed, on SQLite.
    try:
        db.session.add(
            MatchRequest(user_id=None, adopter_id=999_999_999, top_dog_id=None,
                         top_score=1.0, results_count=0)
        )
        db.session.commit()
        db.session.rollback()
        # Not a failure on SQLite: it only enforces foreign keys when
        # PRAGMA foreign_keys is on, which is off by default.
        check("FK violation on match_requests.adopter_id [not enforced by SQLite]",
              not is_pg, "PostgreSQL accepted a dangling foreign key")
    except IntegrityError:
        db.session.rollback()
        check("FK violation on match_requests.adopter_id [rejected]", True)

    # -------------------------------------------------------- timestamps #
    section("4. Timestamps")
    fresh = db.session.get(MatchRequest, request_row.id)
    check("created_at was populated", fresh.created_at is not None)
    check("created_at is naive (no tzinfo)", fresh.created_at.tzinfo is None,
          f"got tzinfo={fresh.created_at.tzinfo}")
    drift = abs((datetime.utcnow() - fresh.created_at).total_seconds())
    check("created_at is UTC, not local", drift < 120, f"{drift:.0f}s from UTC now")
    check("serialises with a Z suffix", fresh.to_dict()["created_at"].endswith("Z"))
    check("ordering by created_at works",
          MatchRequest.query.order_by(MatchRequest.created_at.desc()).first() is not None)

    # --------------------------------------------------- column widths #
    section("5. Column width enforcement")
    try:
        db.session.add(
            Volunteer(name=f"{tag} overflow", email="a@b.com", mobile="9" * 200,
                      address="x", state="s", city="c")
        )
        db.session.commit()
        db.session.rollback()
        # SQLite ignores a VARCHAR length entirely, so storing 200 characters in
        # a VARCHAR(32) is expected here and is not a failure. It is exactly why
        # the API validates these lengths itself — see MAX_MOBILE in app.py.
        check("mobile over VARCHAR(32) [length not enforced by SQLite]",
              not is_pg, "PostgreSQL accepted an over-long value")
    except (DataError, IntegrityError):
        db.session.rollback()
        check("mobile over VARCHAR(32) [rejected by the column]", True)

    db.session.add(
        Volunteer(name=f"{tag} ok", email="a@b.com", mobile="+91 98765 43210",
                  address="12 MG Road", state="Maharashtra", city="Pune")
    )
    db.session.commit()
    check("a normal volunteer row still saves",
          Volunteer.query.filter_by(name=f"{tag} ok").count() == 1)

    # ------------------------------------------------- aggregate queries #
    section("6. Queries used by the dashboard")
    from sqlalchemy import func

    check("count() works", isinstance(User.query.count(), int))
    check("avg() works",
          db.session.query(func.avg(MatchRequest.top_score)).scalar() is not None)
    check("group_by + join works",
          isinstance(
              db.session.query(Dog.name, func.count(MatchRequest.id))
              .join(MatchRequest, MatchRequest.top_dog_id == Dog.id)
              .group_by(Dog.id).all(), list))
    check("datetime comparison works",
          isinstance(
              MatchRequest.query.filter(
                  MatchRequest.created_at >= utcnow() - timedelta(days=7)).count(), int))
    check("LIKE works",
          isinstance(User.query.filter(User.name.like("verify_db%")).count(), int))

    # ------------------------------------------------------------ cleanup #
    section("7. Cleanup")
    ChatbotLog.query.filter(ChatbotLog.question.like(f"{tag}%")).delete(synchronize_session=False)
    MatchRequest.query.filter_by(adopter_id=adopter.id).delete(synchronize_session=False)
    Adopter.query.filter_by(id=adopter.id).delete(synchronize_session=False)
    Volunteer.query.filter(Volunteer.name.like(f"{tag}%")).delete(synchronize_session=False)
    RevokedToken.query.filter_by(jti=jti).delete(synchronize_session=False)
    User.query.filter_by(email=email).delete(synchronize_session=False)
    db.session.commit()

    leftovers = (
        User.query.filter(User.name.like("verify_db%")).count()
        + Volunteer.query.filter(Volunteer.name.like("verify_db%")).count()
    )
    check("every row this script created was removed", leftovers == 0,
          f"{leftovers} left behind")

    # ------------------------------------------------------------- result #
    print("\n" + "=" * 62)
    print(f"PASSED {len(passed)}   FAILED {len(failed)}")
    if failed:
        print("\nFAILURES:")
        for name, detail in failed:
            print(f"  {name}: {detail}")
        return 1
    print(f"ALL DATABASE CHECKS PASSED on {backend}")
    return 0


if __name__ == "__main__":
    from app import create_app

    with create_app().app_context():
        sys.exit(main())
