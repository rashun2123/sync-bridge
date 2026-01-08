from __future__ import annotations

from dataclasses import dataclass
import logging

from sqlalchemy.orm import Session

from app.models.sync_job import SyncJob


@dataclass(frozen=True)
class JobContext:
    db: Session
    job: SyncJob
    logger: logging.Logger
