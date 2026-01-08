from __future__ import annotations

from datetime import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import as_utc, utcnow
from app.models.sync_job import JobPriority, SyncJob, SyncJobStatus
from app.models.sync_job_attempt import SyncJobAttempt


class DuplicateActiveJobError(Exception):
    def __init__(self, *, job_type: str, entity_id: str, existing_job_id: int):
        self.job_type = job_type
        self.entity_id = entity_id
        self.existing_job_id = existing_job_id
        super().__init__(f"active job already exists for {job_type}:{entity_id}")


class JobService:
    def __init__(self, db: Session):
        self._db = db

    def enqueue_sync_job(
        self,
        *,
        job_type: str,
        source_system: str,
        target_system: str,
        entity_type: str,
        entity_id: str,
        max_retries: int | None = None,
        priority: JobPriority | None = None,
        scheduled_at: datetime | None = None,
        payload_version: int = 1,
    ) -> SyncJob:
        existing_job_id = self._find_active_job_id(job_type=job_type, entity_id=entity_id)
        if existing_job_id is not None:
            raise DuplicateActiveJobError(job_type=job_type, entity_id=entity_id, existing_job_id=existing_job_id)

        now = utcnow()
        correlation_id = uuid.uuid4().hex
        scheduled_at_utc = as_utc(scheduled_at)
        job = SyncJob(
            job_type=job_type,
            source_system=source_system,
            target_system=target_system,
            entity_type=entity_type,
            entity_id=entity_id,
            status=SyncJobStatus.pending,
            priority=priority if priority is not None else JobPriority.normal,
            scheduled_at=scheduled_at_utc,
            max_retries=max_retries if max_retries is not None else settings.job_max_retries_default,
            attempt_count=0,
            payload_version=payload_version,
            correlation_id=correlation_id,
            lease_owner=None,
            lease_acquired_at=None,
            lease_expires_at=None,
            created_at=now,
            updated_at=now,
            next_run_at=now,
            last_started_at=None,
            last_finished_at=None,
            last_error=None,
            last_error_type=None,
            last_duration_ms=None,
            canceled_at=None,
            dead_at=None,
            dead_error=None,
            dead_error_type=None,
            is_replay=False,
            replay_of_job_id=None,
            replay_of_attempt_id=None,
        )
        self._db.add(job)
        self._db.commit()
        self._db.refresh(job)
        return job

    def enqueue_replay_job(self, *, job: SyncJob, attempt_id: int) -> SyncJob:
        existing_job_id = self._find_active_job_id(job_type=job.job_type, entity_id=job.entity_id)
        if existing_job_id is not None:
            raise DuplicateActiveJobError(
                job_type=job.job_type,
                entity_id=job.entity_id,
                existing_job_id=existing_job_id,
            )

        now = utcnow()
        replay = SyncJob(
            job_type=job.job_type,
            source_system=job.source_system,
            target_system=job.target_system,
            entity_type=job.entity_type,
            entity_id=job.entity_id,
            status=SyncJobStatus.pending,
            priority=job.priority,
            scheduled_at=None,
            max_retries=job.max_retries,
            attempt_count=0,
            payload_version=job.payload_version,
            correlation_id=uuid.uuid4().hex,
            lease_owner=None,
            lease_acquired_at=None,
            lease_expires_at=None,
            created_at=now,
            updated_at=now,
            next_run_at=now,
            last_started_at=None,
            last_finished_at=None,
            last_error=None,
            last_error_type=None,
            last_duration_ms=None,
            canceled_at=None,
            dead_at=None,
            dead_error=None,
            dead_error_type=None,
            is_replay=True,
            replay_of_job_id=job.id,
            replay_of_attempt_id=attempt_id,
        )
        self._db.add(replay)
        self._db.commit()
        self._db.refresh(replay)
        return replay

    def cancel_job(self, job_id: int) -> SyncJob:
        job = self._db.get(SyncJob, job_id)
        if job is None:
            raise KeyError("job not found")

        if job.status not in {SyncJobStatus.pending, SyncJobStatus.running}:
            raise ValueError("job cannot be canceled")

        now = utcnow()
        job.status = SyncJobStatus.canceled
        job.canceled_at = now
        job.updated_at = now
        job.next_run_at = None
        job.lease_owner = None
        job.lease_acquired_at = None
        job.lease_expires_at = None
        if job.last_finished_at is None:
            job.last_finished_at = now

        self._db.add(job)
        self._db.commit()
        self._db.refresh(job)
        return job

    def retry_job(self, job_id: int) -> SyncJob:
        job = self._db.get(SyncJob, job_id)
        if job is None:
            raise KeyError("job not found")

        if job.status != SyncJobStatus.failed:
            raise ValueError("job cannot be retried")

        now = utcnow()
        job.status = SyncJobStatus.pending
        job.updated_at = now
        job.next_run_at = now
        job.last_error = None
        job.last_error_type = None
        job.last_duration_ms = None
        job.last_started_at = None
        job.last_finished_at = None

        self._db.add(job)
        self._db.commit()
        self._db.refresh(job)
        return job

    def replay_failed_attempt(self, *, job_id: int, attempt_id: int | None) -> SyncJob:
        job = self._db.get(SyncJob, job_id)
        if job is None:
            raise KeyError("job not found")

        if attempt_id is None:
            stmt = (
                select(SyncJobAttempt)
                .where(SyncJobAttempt.job_id == job_id)
                .order_by(SyncJobAttempt.attempt_number.desc())
                .limit(1)
            )
            attempt = self._db.execute(stmt).scalar_one_or_none()
        else:
            attempt = self._db.get(SyncJobAttempt, attempt_id)
            if attempt is not None and attempt.job_id != job_id:
                attempt = None

        if attempt is None:
            raise KeyError("attempt not found")
        if attempt.success:
            raise ValueError("attempt is not a failure")

        return self.enqueue_replay_job(job=job, attempt_id=attempt.id)

    def _find_active_job_id(self, *, job_type: str, entity_id: str) -> int | None:
        stmt = (
            select(SyncJob.id)
            .where(
                SyncJob.job_type == job_type,
                SyncJob.entity_id == entity_id,
                SyncJob.status.in_([SyncJobStatus.pending, SyncJobStatus.running]),
            )
            .order_by(SyncJob.id.desc())
            .limit(1)
        )
        return self._db.execute(stmt).scalar_one_or_none()

    def get_job(self, job_id: int) -> SyncJob | None:
        return self._db.get(SyncJob, job_id)
