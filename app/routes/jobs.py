from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.sync_job import JobPriority, SyncJob, SyncJobStatus
from app.models.sync_job_attempt import SyncJobAttempt
from app.services.job_service import DuplicateActiveJobError, JobService


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class EnqueueJobRequest(BaseModel):
    entity_id: str
    max_retries: int | None = None
    priority: JobPriority | None = None
    scheduled_at: datetime | None = None
    payload_version: int = 1


class JobResponse(BaseModel):
    id: int
    job_type: str
    source_system: str
    target_system: str
    entity_type: str
    entity_id: str
    status: SyncJobStatus
    priority: JobPriority
    scheduled_at: datetime | None
    max_retries: int
    attempt_count: int
    payload_version: int
    correlation_id: str | None
    created_at: datetime
    updated_at: datetime
    next_run_at: datetime | None
    last_started_at: datetime | None
    last_finished_at: datetime | None
    last_error: str | None
    last_error_type: str | None
    last_duration_ms: int | None


class JobAttemptResponse(BaseModel):
    id: int
    attempt_number: int
    started_at: datetime
    finished_at: datetime | None
    success: bool
    error_summary: str | None
    error_type: str | None
    duration_ms: int | None


class ReplayRequest(BaseModel):
    attempt_id: int | None = None


@router.post("/customer", response_model=JobResponse)
def enqueue_customer_sync(
    body: EnqueueJobRequest,
    db: Session = Depends(get_db),
) -> JobResponse:
    try:
        job = JobService(db).enqueue_sync_job(
            job_type="customer_sync",
            source_system="crm",
            target_system="billing",
            entity_type="customer",
            entity_id=body.entity_id,
            max_retries=body.max_retries,
            priority=body.priority,
            scheduled_at=body.scheduled_at,
            payload_version=body.payload_version,
        )
    except DuplicateActiveJobError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "active job already exists",
                "job_type": exc.job_type,
                "entity_id": exc.entity_id,
                "existing_job_id": exc.existing_job_id,
            },
        ) from exc
    return JobResponse.model_validate(job, from_attributes=True)


@router.post("/{job_id}/retry", response_model=JobResponse)
def retry_job(job_id: int, db: Session = Depends(get_db)) -> JobResponse:
    try:
        job = JobService(db).retry_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobResponse.model_validate(job, from_attributes=True)


@router.post("/{job_id}/cancel", response_model=JobResponse)
def cancel_job(job_id: int, db: Session = Depends(get_db)) -> JobResponse:
    try:
        job = JobService(db).cancel_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="job not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobResponse.model_validate(job, from_attributes=True)


@router.post("/{job_id}/replay", response_model=JobResponse)
def replay_failed_attempt(job_id: int, body: ReplayRequest, db: Session = Depends(get_db)) -> JobResponse:
    try:
        replay = JobService(db).replay_failed_attempt(job_id=job_id, attempt_id=body.attempt_id)
    except DuplicateActiveJobError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "active job already exists",
                "job_type": exc.job_type,
                "entity_id": exc.entity_id,
                "existing_job_id": exc.existing_job_id,
            },
        ) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JobResponse.model_validate(replay, from_attributes=True)


@router.post("/invoice", response_model=JobResponse)
def enqueue_invoice_sync(
    body: EnqueueJobRequest,
    db: Session = Depends(get_db),
) -> JobResponse:
    try:
        job = JobService(db).enqueue_sync_job(
            job_type="invoice_sync",
            source_system="crm",
            target_system="billing",
            entity_type="invoice",
            entity_id=body.entity_id,
            max_retries=body.max_retries,
            priority=body.priority,
            scheduled_at=body.scheduled_at,
            payload_version=body.payload_version,
        )
    except DuplicateActiveJobError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "active job already exists",
                "job_type": exc.job_type,
                "entity_id": exc.entity_id,
                "existing_job_id": exc.existing_job_id,
            },
        ) from exc
    return JobResponse.model_validate(job, from_attributes=True)


@router.get("", response_model=list[JobResponse])
def list_jobs(db: Session = Depends(get_db)) -> list[JobResponse]:
    stmt = select(SyncJob).order_by(desc(SyncJob.created_at)).limit(200)
    jobs = list(db.execute(stmt).scalars().all())
    return [JobResponse.model_validate(j, from_attributes=True) for j in jobs]


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: int, db: Session = Depends(get_db)) -> JobResponse:
    job = db.get(SyncJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobResponse.model_validate(job, from_attributes=True)


@router.get("/{job_id}/attempts", response_model=list[JobAttemptResponse])
def get_job_attempts(job_id: int, db: Session = Depends(get_db)) -> list[JobAttemptResponse]:
    job = db.get(SyncJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")

    stmt = (
        select(SyncJobAttempt)
        .where(SyncJobAttempt.job_id == job_id)
        .order_by(desc(SyncJobAttempt.attempt_number))
    )
    attempts = list(db.execute(stmt).scalars().all())
    return [JobAttemptResponse.model_validate(a, from_attributes=True) for a in attempts]
