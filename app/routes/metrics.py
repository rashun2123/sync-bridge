from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.sync_job import SyncJob, SyncJobStatus
from app.models.sync_job_attempt import SyncJobAttempt


router = APIRouter(tags=["metrics"])


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)) -> dict:
    total_jobs = db.execute(select(func.count()).select_from(SyncJob)).scalar_one()

    finished_total = db.execute(
        select(func.count()).select_from(SyncJob).where(SyncJob.status.in_([SyncJobStatus.success, SyncJobStatus.failed, SyncJobStatus.dead]))
    ).scalar_one()
    finished_success = db.execute(
        select(func.count()).select_from(SyncJob).where(SyncJob.status == SyncJobStatus.success)
    ).scalar_one()

    success_rate = (finished_success / finished_total) if finished_total else None

    retry_count = db.execute(
        select(
            func.coalesce(
                func.sum(
                    case(
                        (SyncJob.attempt_count > 1, SyncJob.attempt_count - 1),
                        else_=0,
                    )
                ),
                0,
            )
        ).select_from(SyncJob)
    ).scalar_one()

    avg_execution_ms = db.execute(
        select(func.avg(SyncJobAttempt.duration_ms)).where(SyncJobAttempt.duration_ms.is_not(None))
    ).scalar_one()

    return {
        "total_jobs": int(total_jobs),
        "finished_jobs": int(finished_total),
        "success_rate": float(success_rate) if success_rate is not None else None,
        "retry_count": int(retry_count or 0),
        "avg_execution_ms": float(avg_execution_ms) if avg_execution_ms is not None else None,
    }
