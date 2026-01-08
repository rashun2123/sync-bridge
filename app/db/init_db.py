from sqlalchemy import text

from app import models
from app.core.config import settings
from app.db.base import Base
from app.db.session import SessionLocal, engine


def init_db() -> None:
    Base.metadata.create_all(bind=engine)

    if settings.database_url.startswith("sqlite"):
        _migrate_sqlite()


def _migrate_sqlite() -> None:
    with SessionLocal() as db:
        _rebuild_sync_jobs_if_needed(db)

        _ensure_columns(
            db,
            table="sync_jobs",
            columns=[
                ("priority", "TEXT NOT NULL DEFAULT 'normal'"),
                ("scheduled_at", "DATETIME"),
                ("payload_version", "INTEGER NOT NULL DEFAULT 1"),
                ("correlation_id", "TEXT"),
                ("lease_owner", "TEXT"),
                ("lease_acquired_at", "DATETIME"),
                ("lease_expires_at", "DATETIME"),
                ("last_error_type", "TEXT"),
                ("last_duration_ms", "INTEGER"),
                ("canceled_at", "DATETIME"),
                ("dead_at", "DATETIME"),
                ("dead_error", "TEXT"),
                ("dead_error_type", "TEXT"),
                ("is_replay", "INTEGER NOT NULL DEFAULT 0"),
                ("replay_of_job_id", "INTEGER"),
                ("replay_of_attempt_id", "INTEGER"),
            ],
        )

        _ensure_columns(
            db,
            table="sync_job_attempts",
            columns=[
                ("error_type", "TEXT"),
                ("duration_ms", "INTEGER"),
            ],
        )


def _rebuild_sync_jobs_if_needed(db) -> None:
    row = db.execute(
        text("SELECT sql FROM sqlite_master WHERE type='table' AND name='sync_jobs'")
    ).fetchone()
    if row is None or row[0] is None:
        return

    create_sql = row[0]
    if "CHECK" not in create_sql.upper():
        return

    db.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS sync_jobs_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              job_type TEXT NOT NULL,
              source_system TEXT NOT NULL,
              target_system TEXT NOT NULL,
              entity_type TEXT NOT NULL,
              entity_id TEXT NOT NULL,
              status TEXT NOT NULL,
              priority TEXT NOT NULL DEFAULT 'normal',
              scheduled_at DATETIME,
              max_retries INTEGER NOT NULL,
              attempt_count INTEGER NOT NULL DEFAULT 0,
              payload_version INTEGER NOT NULL DEFAULT 1,
              correlation_id TEXT,
              lease_owner TEXT,
              lease_acquired_at DATETIME,
              lease_expires_at DATETIME,
              created_at DATETIME NOT NULL,
              updated_at DATETIME NOT NULL,
              next_run_at DATETIME,
              last_started_at DATETIME,
              last_finished_at DATETIME,
              last_error TEXT,
              last_error_type TEXT,
              last_duration_ms INTEGER,
              canceled_at DATETIME,
              dead_at DATETIME,
              dead_error TEXT,
              dead_error_type TEXT,
              is_replay INTEGER NOT NULL DEFAULT 0,
              replay_of_job_id INTEGER,
              replay_of_attempt_id INTEGER
            )
            """
        )
    )

    db.execute(
        text(
            """
            INSERT INTO sync_jobs_new (
              id, job_type, source_system, target_system, entity_type, entity_id, status,
              max_retries, attempt_count,
              created_at, updated_at,
              next_run_at, last_started_at, last_finished_at, last_error
            )
            SELECT
              id, job_type, source_system, target_system, entity_type, entity_id, status,
              max_retries, COALESCE(attempt_count, 0),
              created_at, updated_at,
              next_run_at, last_started_at, last_finished_at, last_error
            FROM sync_jobs
            """
        )
    )

    db.execute(text("DROP TABLE sync_jobs"))
    db.execute(text("ALTER TABLE sync_jobs_new RENAME TO sync_jobs"))
    db.commit()


def _ensure_columns(db, *, table: str, columns: list[tuple[str, str]]) -> None:
    existing = {
        row[1]
        for row in db.execute(text(f"PRAGMA table_info('{table}')")).fetchall()
    }

    for name, ddl in columns:
        if name in existing:
            continue
        db.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
    db.commit()
