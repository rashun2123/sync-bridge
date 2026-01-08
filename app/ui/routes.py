from __future__ import annotations

from fastapi import APIRouter, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.sync_job import SyncJob, SyncJobStatus
from app.models.sync_job_attempt import SyncJobAttempt
from app.services.job_service import DuplicateActiveJobError, JobService


templates = Jinja2Templates(directory="app/ui/templates")
router = APIRouter(prefix="/ui", tags=["ui"], include_in_schema=False)


@router.get("/jobs", response_class=HTMLResponse)
def ui_jobs(request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    status = request.query_params.get("status")

    stmt = select(SyncJob)
    if status:
        try:
            stmt = stmt.where(SyncJob.status == SyncJobStatus(status))
        except ValueError:
            status = None

    stmt = stmt.order_by(desc(SyncJob.created_at)).limit(200)
    jobs = list(db.execute(stmt).scalars().all())
    return templates.TemplateResponse(
        "jobs.html",
        {"request": request, "title": "Jobs", "jobs": jobs, "status_filter": status},
    )


@router.post("/jobs/enqueue")
def ui_enqueue_customer_sync(
    entity_id: str = Form(...),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    try:
        JobService(db).enqueue_sync_job(
            job_type="customer_sync",
            source_system="crm",
            target_system="billing",
            entity_type="customer",
            entity_id=entity_id,
            max_retries=None,
        )
    except DuplicateActiveJobError as exc:
        return RedirectResponse(url=f"/ui/jobs/{exc.existing_job_id}", status_code=303)
    return RedirectResponse(url="/ui/jobs", status_code=303)


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def ui_job_detail(job_id: int, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    job = JobService(db).get_job(job_id)
    if job is None:
        return templates.TemplateResponse(
            "base.html",
            {"request": request, "title": "Not found"},
            status_code=404,
        )

    stmt = (
        select(SyncJobAttempt)
        .where(SyncJobAttempt.job_id == job_id)
        .order_by(desc(SyncJobAttempt.attempt_number))
    )
    attempts = list(db.execute(stmt).scalars().all())

    return templates.TemplateResponse(
        "job_detail.html",
        {"request": request, "title": f"Job {job_id}", "job": job, "attempts": attempts},
    )


@router.post("/jobs/{job_id}/cancel")
def ui_cancel_job(job_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        JobService(db).cancel_job(job_id)
    finally:
        return RedirectResponse(url=f"/ui/jobs/{job_id}", status_code=303)


@router.post("/jobs/{job_id}/retry")
def ui_retry_job(job_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        JobService(db).retry_job(job_id)
    finally:
        return RedirectResponse(url=f"/ui/jobs/{job_id}", status_code=303)


@router.post("/jobs/{job_id}/replay")
def ui_replay_job(job_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    try:
        replay = JobService(db).replay_failed_attempt(job_id=job_id, attempt_id=None)
        return RedirectResponse(url=f"/ui/jobs/{replay.id}", status_code=303)
    except Exception:
        return RedirectResponse(url=f"/ui/jobs/{job_id}", status_code=303)
