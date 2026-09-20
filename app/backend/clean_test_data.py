"""Remove the rows created by automated verification runs.

    python clean_test_data.py            # dry run — shows what it WOULD delete
    python clean_test_data.py --apply     # actually delete

Only touches rows whose name/email matches a harness pattern. The seeded admin
and demo accounts, the 18 dogs, and anything created by hand are never matched.
Anything removed can be regenerated with `python demo_data.py`.
"""

from __future__ import annotations

import sys

from models import Adopter, ChatbotLog, MatchRequest, User, Volunteer, db

# Names/emails the test harnesses generate. Deliberately narrow.
USER_PATTERNS = ["Journey %", "Phase7 %", "Auth %", "Flow %"]
EMAIL_PATTERNS = ["journey%@test.com", "phase7.%@test.com", "auth%@test.com", "%@test.com"]
VOLUNTEER_PATTERNS = ["Volunteer 17%", "Vol7 %", "Vol %"]


def matching_users():
    q = User.query.filter(User.is_admin.is_(False))
    clauses = [User.name.like(p) for p in USER_PATTERNS]
    clauses += [User.email.like(p) for p in EMAIL_PATTERNS]
    return q.filter(db.or_(*clauses)).all()


def matching_volunteers():
    return Volunteer.query.filter(
        db.or_(*[Volunteer.name.like(p) for p in VOLUNTEER_PATTERNS])
    ).all()


def main(apply: bool) -> None:
    users = matching_users()
    volunteers = matching_volunteers()
    user_ids = [u.id for u in users]

    requests = (
        MatchRequest.query.filter(MatchRequest.user_id.in_(user_ids)).all()
        if user_ids
        else []
    )
    adopters = (
        Adopter.query.filter(Adopter.user_id.in_(user_ids)).all() if user_ids else []
    )
    logs = ChatbotLog.query.filter(ChatbotLog.user_id.in_(user_ids)).all() if user_ids else []

    print(f"test users        : {len(users)}")
    for u in users[:8]:
        print(f"    {u.id:4}  {u.name}  <{u.email}>")
    if len(users) > 8:
        print(f"    ... and {len(users) - 8} more")
    print(f"test volunteers   : {len(volunteers)}")
    print(f"their match reqs  : {len(requests)}")
    print(f"their adopters    : {len(adopters)}")
    print(f"their chat logs   : {len(logs)}")
    print()
    print(f"remaining users after   : {User.query.count() - len(users)}")
    print(f"remaining volunteers    : {Volunteer.query.count() - len(volunteers)}")
    print(f"remaining match requests: {MatchRequest.query.count() - len(requests)}")

    if not apply:
        print("\nDRY RUN — nothing deleted. Re-run with --apply to delete.")
        return

    for row in requests + logs + adopters + volunteers + users:
        db.session.delete(row)
    db.session.commit()
    print("\ndeleted.")


if __name__ == "__main__":
    from app import create_app

    app = create_app()
    with app.app_context():
        main("--apply" in sys.argv)
