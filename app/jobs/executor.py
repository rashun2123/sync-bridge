from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import as_utc, utcnow
from app.integrations.errors import ExternalAPIError
from app.jobs.registry import JobRegistry
from app.jobs.types import JobContext
from app.models.sync_job import SyncJob, SyncJobStatus
from app.models.sync_job_attempt import SyncJobAttempt


class JobExecutor:
    def __init__(self, *, registry: JobRegistry):
        self._registry = registry

    def execute(self, *, db: Session, job_id: int, lease_owner: str) -> None:
        job = db.get(SyncJob, job_id)
        if job is None:
            return

        now = utcnow()
        if job.status != SyncJobStatus.running:
            return
        if job.lease_owner != lease_owner:
            return
        lease_expires_at = as_utc(job.lease_expires_at)
        if lease_expires_at is not None and lease_expires_at <= now:
            return
        if job.status == SyncJobStatus.canceled:
            self._release_lease(db=db, job=job)
            return

        logger = logging.getLogger("syncbridge.jobs")
        extra = {
            "job_id": job.id,
            "job_type": job.job_type,
            "source_system": job.source_system,
            "target_system": job.target_system,
            "entity_type": job.entity_type,
            "entity_id": job.entity_id,
            "correlation_id": job.correlation_id,
            "replay": bool(job.is_replay),
            "replay_of_job_id": job.replay_of_job_id,
            "replay_of_attempt_id": job.replay_of_attempt_id,
        }

        attempt_number = job.attempt_count + 1

        job.lease_expires_at = now + timedelta(seconds=settings.job_lease_seconds)
        job.attempt_count = attempt_number
        job.last_started_at = now
        job.updated_at = now
        db.add(job)
        db.commit()
        db.refresh(job)

        attempt = SyncJobAttempt(
            job_id=job.id,
            attempt_number=attempt_number,
            started_at=now,
            finished_at=None,
            success=False,
            error_summary=None,
            error_type=None,
            duration_ms=None,
        )
        db.add(attempt)
        db.commit()
        db.refresh(attempt)

        logger.info("job attempt started", extra={**extra, "attempt_number": attempt_number})

        handler = self._registry.get(job.job_type, payload_version=job.payload_version)
        ctx = JobContext(db=db, job=job, logger=logger)

        try:
            handler(ctx)
        except Exception as exc:
            self._mark_failure(db=db, job=job, attempt=attempt, exc=exc)
            logger.error(
                "job attempt failed",
                extra={
                    **extra,
                    "attempt_number": attempt_number,
                    "error_summary": _error_summary(exc),
                },
            )
            return

        self._mark_success(db=db, job=job, attempt=attempt)
        logger.info("job attempt succeeded", extra={**extra, "attempt_number": attempt_number})

    def _mark_success(self, *, db: Session, job: SyncJob, attempt: SyncJobAttempt) -> None:
        now = utcnow()
        job = db.get(SyncJob, job.id) or job

        started_at = as_utc(attempt.started_at) or now
        duration_ms = int((now - started_at).total_seconds() * 1000)

        attempt.success = True
        attempt.error_summary = None
        attempt.error_type = None
        attempt.finished_at = now
        attempt.duration_ms = duration_ms

        if job.status != SyncJobStatus.canceled:
            job.status = SyncJobStatus.success
            job.last_finished_at = now
            job.updated_at = now
            job.next_run_at = None
            job.last_error = None
            job.last_error_type = None
            job.last_duration_ms = duration_ms

        self._release_lease(db=db, job=job)

        db.add(attempt)
        db.add(job)
        db.commit()

    def _mark_failure(self, *, db: Session, job: SyncJob, attempt: SyncJobAttempt, exc: Exception) -> None:
        now = utcnow()
        job = db.get(SyncJob, job.id) or job

        started_at = as_utc(attempt.started_at) or now
        duration_ms = int((now - started_at).total_seconds() * 1000)
        error_type, summary, retryable = _classify_exception(exc)

        attempt.success = False
        attempt.error_summary = summary
        attempt.error_type = error_type
        attempt.finished_at = now
        attempt.duration_ms = duration_ms

        job.last_error = summary
        job.last_error_type = error_type
        job.last_duration_ms = duration_ms
        job.updated_at = now

        if job.status == SyncJobStatus.canceled:
            self._release_lease(db=db, job=job)
        elif retryable and job.attempt_count <= job.max_retries:
            delay_seconds = settings.job_backoff_seconds_base * (2 ** (job.attempt_count - 1))
            job.status = SyncJobStatus.pending
            job.next_run_at = now + timedelta(seconds=delay_seconds)
            self._release_lease(db=db, job=job)
        elif retryable:
            job.status = SyncJobStatus.dead
            job.dead_at = now
            job.dead_error = summary
            job.dead_error_type = error_type
            job.last_finished_at = now
            job.next_run_at = None
            self._release_lease(db=db, job=job)
        else:
            job.status = SyncJobStatus.failed
            job.last_finished_at = now
            job.next_run_at = None

            self._release_lease(db=db, job=job)

        db.add(attempt)
        db.add(job)
        db.commit()

    def _release_lease(self, *, db: Session, job: SyncJob) -> None:
        job.lease_owner = None
        job.lease_acquired_at = None
        job.lease_expires_at = None
        db.add(job)


def _error_summary(exc: Exception) -> str:
    text = str(exc).strip()
    if text:
        return text[:1024]
    return exc.__class__.__name__


def _classify_exception(exc: Exception) -> tuple[str, str, bool]:
    if isinstance(exc, ExternalAPIError):
        code = exc.status_code
        if code is None or code >= 500:
            return "UpstreamTimeout", _error_summary(exc), True
        if code == 429:
            return "UpstreamRateLimited", _error_summary(exc), True
        if code == 404:
            return "NotFound", _error_summary(exc), False
        return "ValidationError", _error_summary(exc), False

    return "ValidationError", _error_summary(exc), False
