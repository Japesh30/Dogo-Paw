"""
Checks for the migration foundation (schema.py + migrations/).

Every scenario starts the real app in a subprocess against its own throwaway
SQLite file, because app.py builds the app at import time. The development
database is never touched, and DATABASE_URL is overridden explicitly so this
can never reach a hosted database by accident.

    python test_migrations.py
    python test_migrations.py --postgres postgresql://...   # also run on Postgres

The --postgres URL must point at an EMPTY, disposable database: the script
creates and drops tables in it.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAILURES: list[str] = []


def check(label: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {label}" + (f"  ({detail})" if detail and not condition else ""))
    if not condition:
        FAILURES.append(label)


def run(url: str, code: str, **env) -> subprocess.CompletedProcess:
    """Run `code` in a fresh interpreter with the app pointed at `url`."""
    child_env = {
        **os.environ,
        "DATABASE_URL": url,
        "APP_ENV": "development",
        "PYTHONIOENCODING": "utf-8",
        **env,
    }
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=HERE, env=child_env, capture_output=True, text=True, timeout=300,
    )


START = "import app"

STATE = """
import json, app
from sqlalchemy import inspect, text
from models import db
with app.app.app_context():
    insp = inspect(db.engine)
    tables = sorted(insp.get_table_names())
    counts = {t: db.session.execute(text(f'SELECT COUNT(*) FROM {t}')).scalar()
              for t in tables if t != 'alembic_version'}
    version = db.session.execute(text('SELECT version_num FROM alembic_version')).scalars().all() \
        if 'alembic_version' in tables else None
    print('STATE' + json.dumps({'tables': tables, 'counts': counts, 'version': version}))
"""

# Models vs. the migrated database. An empty diff means the migrations fully
# describe models.py, which is what stops a model change shipping without one.
DRIFT = """
import app
from alembic.migration import MigrationContext
from alembic.autogenerate import compare_metadata
from models import db
with app.app.app_context(), db.engine.connect() as c:
    diff = compare_metadata(MigrationContext.configure(c, opts={'compare_type': True}), db.metadata)
    print('DRIFT' + repr(diff))
"""

DOWNGRADE = """
import app
from flask_migrate import downgrade
with app.app.app_context():
    downgrade(revision='base')  # Flask-Migrate logs the error and exits 1
    print('DOWNGRADE ran')
"""

# Builds a database the old way: create_all() and some rows, no Alembic. By
# default only the seven tables that existed before migrations, which is what
# production actually has; all_tables=True builds every model, for comparing
# against a migrated schema.
LEGACY = """
from sqlalchemy import create_engine, text
from models import db
from schema import BASELINE_SCHEMA
import models
e = create_engine({url!r}.replace('postgresql://', 'postgresql+psycopg://', 1))
tables = None if {all_tables!r} else [db.metadata.tables[t] for t in BASELINE_SCHEMA]
db.metadata.create_all(e, tables=tables)
with e.begin() as c:
    c.execute(text("INSERT INTO users (name,email,password_hash,is_admin,created_at) VALUES ('Old','old@example.com','x',false,'2026-01-01')"))
    c.execute(text("INSERT INTO dogs (id,name,age,energy_level,size,temperament,medical_needs,good_with_kids,good_with_other_pets,created_at) VALUES (1,'Bruno',3,'high','large','energetic',false,true,true,'2026-01-01')"))
    c.execute(text("INSERT INTO adopters (user_id,activity_level,home_type,experience_level,has_kids,has_other_pets,created_at) VALUES (1,'low','apartment','none',false,false,'2026-01-01')"))
    c.execute(text("INSERT INTO match_requests (user_id,adopter_id,top_dog_id,top_score,results_count,created_at) VALUES (1,1,1,80.0,18,'2026-01-01')"))
    c.execute(text("INSERT INTO volunteers (name,email,mobile,address,state,city,submitted_at) VALUES ('V','v@example.com','9876543210','a','s','c','2026-01-01')"))
    c.execute(text("INSERT INTO chatbot_logs (question,predicted_intent,confidence,low_confidence,created_at) VALUES ('hi','greeting',0.9,false,'2026-01-01')"))
    {extra}
"""


def state(url: str) -> dict:
    out = run(url, STATE, DB_AUTO_MIGRATE="false")
    line = next((l for l in out.stdout.splitlines() if l.startswith("STATE")), None)
    return json.loads(line[5:]) if line else {"error": out.stderr[-500:]}


def sqlite_schema(path: Path) -> dict:
    """Columns and indexes per table, for comparing two SQLite files."""
    con = sqlite3.connect(path)
    schema = {}
    for (name,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name != 'alembic_version'"
    ):
        schema[name] = {
            "columns": [row[1:6] for row in con.execute(f"PRAGMA table_info('{name}')")],
            "indexes": sorted(
                (row[1], row[2]) for row in con.execute(f"PRAGMA index_list('{name}')")
            ),
            "fks": sorted(row[2:5] for row in con.execute(f"PRAGMA foreign_key_list('{name}')")),
        }
    con.close()
    return schema


# Every table at the latest migration, and that migration's id. Update both
# when a migration is added; the drift check below catches a model change that
# has no migration.
HEAD = "0004_dog_id_sequence"
HEAD_TABLES = sorted([
    "adopters", "alembic_version", "chatbot_logs", "dogs", "match_requests",
    "revoked_tokens", "users", "volunteers",
    # 0002
    "follow_ups", "health_observations", "medical_records", "medications", "vaccinations",
    # 0003
    "health_alerts", "notifications",
    # 0004 adds no tables: it only advances the dogs id sequence on PostgreSQL.
])


def scenarios(make_url, reset, is_sqlite: bool) -> None:
    print("\n1. Fresh empty database -> baseline creates everything")
    url = make_url("fresh")
    out = run(url, START)
    check("app starts on an empty database", out.returncode == 0, out.stderr[-400:])
    s = state(url)
    check("every table up to head exists", s.get("tables") == HEAD_TABLES, str(s))
    check(f"recorded at {HEAD}", s.get("version") == [HEAD], str(s.get("version")))
    check("18 dogs seeded", s.get("counts", {}).get("dogs") == 18)
    check("admin + demo users seeded", s.get("counts", {}).get("users") == 2)
    drift = run(url, DRIFT, DB_AUTO_MIGRATE="false")
    check("no drift between models.py and migrations", "DRIFT[]" in drift.stdout,
          drift.stdout[-400:] + drift.stderr[-400:])

    print("\n2. Restart is a no-op")
    out = run(url, START)
    s2 = state(url)
    check("second start succeeds", out.returncode == 0, out.stderr[-400:])
    check("no duplicate rows after restart", s2.get("counts") == s.get("counts"))
    check("still one version row", s2.get("version") == [HEAD])

    if is_sqlite:
        print("\n3. Migrated schema is identical to the old create_all() schema")
        legacy_path = Path(make_url("compare").split("///", 1)[1])
        run(make_url("compare"), LEGACY.format(url=make_url("compare"), extra="pass", all_tables=True))
        fresh_path = Path(url.split("///", 1)[1])
        a, b = sqlite_schema(fresh_path), sqlite_schema(legacy_path)
        check("same tables, columns, indexes and foreign keys", a == b,
              json.dumps({k: (a.get(k), b.get(k)) for k in set(a) | set(b) if a.get(k) != b.get(k)})[:600])

    print("\n4. Existing create_all() database with data -> stamped, not recreated")
    reset()
    url = make_url("legacy")
    built = run(url, LEGACY.format(all_tables=False, url=url, extra="pass"))
    check("legacy database built", built.returncode == 0, built.stderr[-400:])
    before = state(url)
    out = run(url, START)
    check("app starts on the legacy database", out.returncode == 0, out.stderr[-600:])
    check("startup reported stamping", "stamped existing schema as 0001_baseline" in out.stdout)
    after = state(url)
    check(f"stamped, then upgraded to {HEAD}", after.get("version") == [HEAD])
    check("upgrade added the medical tables, empty", all(
        after.get("counts", {}).get(t) == 0
        for t in ("medical_records", "vaccinations", "medications", "health_observations", "follow_ups")))
    check("no table removed", set(before["tables"]) <= set(after.get("tables", [])))
    for table in ("adopters", "match_requests", "volunteers", "chatbot_logs"):
        check(f"{table} rows preserved", after["counts"].get(table) == before["counts"].get(table))
    check("existing user kept, seeded accounts added",
          after["counts"].get("users") == before["counts"]["users"] + 2)
    check("dogs: existing row kept, none duplicated", after["counts"].get("dogs") == 1)
    drift = run(url, DRIFT, DB_AUTO_MIGRATE="false")
    check("no drift on the stamped database", "DRIFT[]" in drift.stdout, drift.stdout[-400:])

    print("\n5. Pre-Phase-6 database (dogs without photo_url/bio)")
    reset()
    url = make_url("prephase6")
    run(url, LEGACY.format(all_tables=False,
        url=url,
        extra="c.execute(text('ALTER TABLE dogs DROP COLUMN photo_url')); "
              "c.execute(text('ALTER TABLE dogs DROP COLUMN bio'))",
    ))
    out = run(url, START)
    check("app starts and patches the columns", out.returncode == 0, out.stderr[-600:])
    check("columns added before stamping", "migrated dogs: added photo_url, bio" in out.stdout)
    check(f"stamped, then upgraded to {HEAD}", state(url).get("version") == [HEAD])

    print("\n6. Incomplete legacy database -> refuses to start, stamps nothing")
    reset()
    url = make_url("broken")
    run(url, LEGACY.format(all_tables=False, url=url, extra="c.execute(text('DROP TABLE volunteers'))"))
    out = run(url, START)
    check("startup fails", out.returncode != 0)
    check("error names the missing table", "table volunteers" in out.stderr, out.stderr[-400:])
    s = state(url)
    check("no version stamped", s.get("version") in (None, []), str(s.get("version")))
    check("missing table not silently created", "volunteers" not in s.get("tables", []))

    print("\n7. Downgrade past the baseline is refused")
    reset()
    url = make_url("downgrade")
    run(url, START)
    out = run(url, DOWNGRADE, DB_AUTO_MIGRATE="false")
    check("downgrade refused",
          out.returncode != 0 and "DOWNGRADE ran" not in out.stdout
          and "Refusing to downgrade past the baseline" in out.stderr,
          out.stdout[-300:] + out.stderr[-300:])
    check("tables still there", state(url).get("counts", {}).get("dogs") == 18)

    print("\n8. DB_AUTO_MIGRATE=false leaves the database alone")
    reset()
    url = make_url("nomigrate")
    out = run(url, START, DB_AUTO_MIGRATE="false")
    check("app imports", out.returncode == 0, out.stderr[-300:])
    check("nothing created", state(url).get("tables") == [])


def main() -> int:
    pg_url = sys.argv[sys.argv.index("--postgres") + 1] if "--postgres" in sys.argv else None

    if pg_url:
        from sqlalchemy.engine import make_url

        # This drops the whole public schema between scenarios. A hosted URL
        # pasted here by mistake would wipe production, so only a database on
        # this machine is accepted, and that is checked before anything runs.
        host = make_url(pg_url).host
        if host not in {"localhost", "127.0.0.1", "::1"}:
            print(f"refusing to run against {host!r}: --postgres must be a local, disposable database")
            return 2

    with tempfile.TemporaryDirectory() as tmp:
        print("=== SQLite ===")
        scenarios(
            make_url=lambda name: f"sqlite:///{Path(tmp) / (name + '.db')}",
            reset=lambda: None,
            is_sqlite=True,
        )

    if pg_url:
        from sqlalchemy import create_engine, text

        def reset_pg():
            engine = create_engine(pg_url.replace("postgresql://", "postgresql+psycopg://", 1))
            with engine.begin() as c:
                c.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
            engine.dispose()

        print("\n=== PostgreSQL ===")
        reset_pg()
        scenarios(make_url=lambda name: pg_url, reset=reset_pg, is_sqlite=False)
        reset_pg()

    total = "all passed" if not FAILURES else f"{len(FAILURES)} FAILED: {FAILURES}"
    print(f"\n{total}")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
