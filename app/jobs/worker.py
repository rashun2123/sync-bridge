from __future__ import annotations

import logging
import threading
import time
import uuid
from datetime import timedelta

from sqlalchemy import and_, case, or_, select, update

from app.core.config import settings
from app.core.time import utcnow
from app.db.session import SessionLocal
from app.jobs.executor import JobExecutor
from app.models.sync_job import JobPriority, SyncJob, SyncJobStatus


class InProcessWorker:
    def __init__(self, *, executor: JobExecutor, poll_interval_seconds: float = 1.0):
        self._executor = executor
        self._poll_interval_seconds = poll_interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._logger = logging.getLogger("syncbridge.worker")
        self._lease_owner = uuid.uuid4().hex

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="syncbridge-worker", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        self._logger.info("worker started")
        while not self._stop_event.is_set():
            try:
                claimed = self._claim_next_job_id()
                if claimed is None:
                    time.sleep(self._poll_interval_seconds)
                    continue

                job_id, lease_owner = claimed
                with SessionLocal() as db:
                    self._executor.execute(db=db, job_id=job_id, lease_owner=lease_owner)
            except Exception as exc:
                self._logger.error("worker loop error", extra={"error_summary": str(exc)[:1024]})
                time.sleep(self._poll_interval_seconds)

        self._logger.info("worker stopped")

    def _claim_next_job_id(self) -> tuple[int, str] | None:
        now = utcnow()
        lease_expires_at = now + timedelta(seconds=settings.job_lease_seconds)
        with SessionLocal() as db:
            eligible = or_(
                SyncJob.status == SyncJobStatus.pending,
                and_(
                    SyncJob.status == SyncJobStatus.running,
                    SyncJob.lease_expires_at.is_not(None),
                    SyncJob.lease_expires_at <= now,
                ),
            )

            due = and_(
                or_(SyncJob.next_run_at.is_(None), SyncJob.next_run_at <= now),
                or_(SyncJob.scheduled_at.is_(None), SyncJob.scheduled_at <= now),
            )

            priority_rank = case(
                (SyncJob.priority == JobPriority.high, 2),
                (SyncJob.priority == JobPriority.normal, 1),
                else_=0,
            )

            stmt = (
                select(SyncJob.id)
                .where(
                    and_(eligible, due)
                )
                .order_by(
                    priority_rank.desc(),
                    SyncJob.scheduled_at.asc().nullsfirst(),
                    SyncJob.next_run_at.asc().nullsfirst(),
                    SyncJob.id.asc(),
                )
                .limit(1)
            )
            job_id = db.execute(stmt).scalar_one_or_none()
            if job_id is None:
                return None

            claim_stmt = (
                update(SyncJob)
                .where(
                    SyncJob.id == job_id,
                    eligible,
                    due,
                )
                .values(
                    status=SyncJobStatus.running,
                    lease_owner=self._lease_owner,
                    lease_acquired_at=now,
                    lease_expires_at=lease_expires_at,
                    updated_at=now,
                )
            )

            res = db.execute(claim_stmt)
            if res.rowcount != 1:
                db.rollback()
                return None
            db.commit()
            return job_id, self._lease_owner
