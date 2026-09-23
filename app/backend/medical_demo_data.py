"""Demo medical records for local development and tests. Never production.

Five of the seeded dogs get a small, deterministic history that exercises what
later phases need to read: a vaccination history with one booster coming due,
medication courses (active, completed), a falling weight series, a raised
temperature, and follow-ups in every state.

    python medical_demo_data.py            # add, if not already there
    python medical_demo_data.py --clear    # remove fixture rows only

Dates are offsets from an anchor day (today by default) so "due soon" stays due
soon; the tests pass a fixed anchor so they are fully reproducible.

Every row carries DEMO_TAG in its notes/description, which is how --clear finds
exactly the rows this script made and nothing an admin typed in. The script
refuses to run against anything but SQLite or a database on this machine, and
never under APP_ENV=production.

The values are illustrative data for testing software, not veterinary advice.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

from sqlalchemy.engine import make_url

from models import FollowUp, HealthObservation, MedicalRecord, Medication, Vaccination, db

DEMO_TAG = "[demo]"
MODELS = (MedicalRecord, Vaccination, Medication, HealthObservation, FollowUp)


def fixture(anchor: date) -> list:
    """The demo rows, relative to `anchor`."""

    def ago(days: int) -> date:
        return anchor - timedelta(days=days)

    def ahead(days: int) -> date:
        return anchor + timedelta(days=days)

    rows = []

    # Bruno (1): healthy young dog. Core vaccines done; one booster due soon.
    rows += [
        Vaccination(dog_id=1, vaccine_name="DHPP", administered_date=ago(340),
                    next_due_date=ahead(25), status="completed", veterinarian="Dr. A. Rao",
                    notes=f"{DEMO_TAG} Annual core vaccine."),
        Vaccination(dog_id=1, vaccine_name="Rabies", administered_date=ago(340),
                    next_due_date=ahead(390), status="completed", veterinarian="Dr. A. Rao",
                    notes=DEMO_TAG),
        MedicalRecord(dog_id=1, record_type="checkup", title="Intake examination",
                      description=f"{DEMO_TAG} Routine intake check, no concerns noted.",
                      veterinarian="Dr. A. Rao", visit_date=ago(340)),
        HealthObservation(dog_id=1, observation_date=ago(60), weight_kg=31.2,
                          temperature_c=38.6, notes=DEMO_TAG),
        HealthObservation(dog_id=1, observation_date=ago(5), weight_kg=31.5,
                          temperature_c=38.7, notes=DEMO_TAG),
    ]

    # Rocky (4): ongoing medication; weight falling over three months, one
    # raised temperature, and a follow-up that was missed.
    rows += [
        Medication(dog_id=4, medication_name="Phenobarbital", dosage="1 tablet",
                   frequency="twice daily", start_date=ago(200), status="active",
                   prescribed_by="Dr. S. Menon", notes=f"{DEMO_TAG} Long-term course."),
        MedicalRecord(dog_id=4, record_type="diagnostic", title="Blood panel",
                      description=f"{DEMO_TAG} Routine monitoring bloods.",
                      veterinarian="Dr. S. Menon", visit_date=ago(95)),
        HealthObservation(dog_id=4, observation_date=ago(90), weight_kg=34.0,
                          temperature_c=38.5, notes=DEMO_TAG),
        HealthObservation(dog_id=4, observation_date=ago(60), weight_kg=32.9,
                          temperature_c=38.6, notes=DEMO_TAG),
        HealthObservation(dog_id=4, observation_date=ago(30), weight_kg=31.6,
                          temperature_c=39.8, symptoms=["lethargy", "reduced appetite"],
                          notes=DEMO_TAG),
        HealthObservation(dog_id=4, observation_date=ago(3), weight_kg=30.4,
                          temperature_c=38.9, symptoms=["reduced appetite"], notes=DEMO_TAG),
        FollowUp(dog_id=4, reason="Recheck medication levels", due_date=ago(14),
                 status="missed", notes=DEMO_TAG),
        FollowUp(dog_id=4, reason="Weight review", due_date=ahead(7),
                 status="pending", notes=DEMO_TAG),
    ]

    # Max (8): daily medication with regular check-ups, all kept up to date.
    rows += [
        Medication(dog_id=8, medication_name="Levothyroxine", dosage="1 tablet",
                   frequency="once daily", start_date=ago(400), status="active",
                   prescribed_by="Dr. A. Rao", notes=DEMO_TAG),
        MedicalRecord(dog_id=8, record_type="checkup", title="Thyroid recheck",
                      description=f"{DEMO_TAG} Stable on current dose.",
                      veterinarian="Dr. A. Rao", visit_date=ago(45)),
        FollowUp(dog_id=8, reason="Thyroid recheck", due_date=ago(45),
                 completed_date=ago(45), status="completed", notes=DEMO_TAG),
        FollowUp(dog_id=8, reason="Thyroid recheck", due_date=ahead(135),
                 status="pending", notes=DEMO_TAG),
        HealthObservation(dog_id=8, observation_date=ago(45), weight_kg=29.8,
                          temperature_c=38.4, notes=DEMO_TAG),
    ]

    # Nala (13): older dog with a joint condition; one vaccine now overdue.
    rows += [
        Medication(dog_id=13, medication_name="Carprofen", dosage="1 tablet",
                   frequency="once daily with food", start_date=ago(300), status="active",
                   prescribed_by="Dr. S. Menon", notes=DEMO_TAG),
        Medication(dog_id=13, medication_name="Amoxicillin", dosage="1 tablet",
                   frequency="twice daily", start_date=ago(120), end_date=ago(110),
                   status="completed", prescribed_by="Dr. S. Menon", notes=DEMO_TAG),
        Vaccination(dog_id=13, vaccine_name="Leptospirosis", administered_date=ago(400),
                    next_due_date=ago(35), status="overdue", notes=DEMO_TAG),
        MedicalRecord(dog_id=13, record_type="treatment", title="Joint assessment",
                      description=f"{DEMO_TAG} Stiffness in hind legs; pain relief continued.",
                      veterinarian="Dr. S. Menon", visit_date=ago(120)),
        HealthObservation(dog_id=13, observation_date=ago(120), weight_kg=21.0,
                          symptoms=["stiffness"], notes=DEMO_TAG),
        HealthObservation(dog_id=13, observation_date=ago(10), weight_kg=21.4,
                          temperature_c=38.3, notes=DEMO_TAG),
    ]

    # Pixie (15): skin condition, recently discontinued one treatment.
    rows += [
        Medication(dog_id=15, medication_name="Oclacitinib", dosage="1 tablet",
                   frequency="once daily", start_date=ago(90), status="active",
                   prescribed_by="Dr. A. Rao", notes=DEMO_TAG),
        Medication(dog_id=15, medication_name="Medicated shampoo", dosage="1 wash",
                   frequency="weekly", start_date=ago(150), end_date=ago(90),
                   status="discontinued", prescribed_by="Dr. A. Rao",
                   notes=f"{DEMO_TAG} Replaced by oral treatment."),
        Vaccination(dog_id=15, vaccine_name="DHPP", next_due_date=ahead(10),
                    status="scheduled", notes=DEMO_TAG),
        MedicalRecord(dog_id=15, record_type="treatment", title="Dermatology consult",
                      description=f"{DEMO_TAG} Itching and hair loss on flanks.",
                      veterinarian="Dr. A. Rao", visit_date=ago(90)),
        HealthObservation(dog_id=15, observation_date=ago(90), weight_kg=6.1,
                          symptoms=["itching", "hair loss"], notes=DEMO_TAG),
        HealthObservation(dog_id=15, observation_date=ago(7), weight_kg=6.2,
                          symptoms=["itching"], notes=DEMO_TAG),
        FollowUp(dog_id=15, reason="Skin recheck", due_date=ahead(21),
                 status="pending", notes=DEMO_TAG),
    ]

    return rows


def _is_demo(model):
    column = model.description if model is MedicalRecord else model.notes
    return column.like(f"{DEMO_TAG}%")


def assert_local_database() -> None:
    """Refuse anything that could be a shared or production database."""
    if os.environ.get("APP_ENV", "").strip().lower() == "production":
        raise SystemExit("Refusing to load demo medical data with APP_ENV=production.")
    url = db.engine.url
    if url.get_backend_name() != "sqlite" and url.host not in {"localhost", "127.0.0.1", "::1"}:
        raise SystemExit(
            f"Refusing to load demo medical data into {url.host!r}: only SQLite or a "
            "database on this machine is allowed."
        )


def load(anchor: date | None = None) -> int:
    """Add the fixture unless it is already there. Returns rows added."""
    assert_local_database()
    if any(model.query.filter(_is_demo(model)).first() for model in MODELS):
        return 0
    rows = fixture(anchor or date.today())
    db.session.add_all(rows)
    db.session.commit()
    return len(rows)


def clear() -> int:
    """Delete fixture rows only. Returns rows removed."""
    assert_local_database()
    removed = sum(
        model.query.filter(_is_demo(model)).delete(synchronize_session=False)
        for model in MODELS
    )
    db.session.commit()
    return removed


if __name__ == "__main__":
    # Guard on the URL before the app starts: create_app() migrates and
    # seeds, and nothing should touch a non-local database from this script.
    raw = os.environ.get("DATABASE_URL", "").strip()
    if raw and not raw.startswith("sqlite"):
        host = make_url(raw.replace("postgres://", "postgresql://", 1)).host
        if host not in {"localhost", "127.0.0.1", "::1"}:
            raise SystemExit(f"Refusing to run against {host!r}: local databases only.")

    from app import app

    with app.app_context():
        if "--clear" in sys.argv:
            print(f"removed {clear()} demo medical rows")
        else:
            added = load()
            print(f"added {added} demo medical rows" if added else "demo medical data already present")
