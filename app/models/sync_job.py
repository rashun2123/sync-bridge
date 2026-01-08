import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class SyncJobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    dead = "dead"
    canceled = "canceled"


class JobPriority(str, enum.Enum):
    low = "low"
    normal = "normal"
    high = "high"


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    job_type: Mapped[str] = mapped_column(String(64), index=True)
    source_system: Mapped[str] = mapped_column(String(64), index=True)
    target_system: Mapped[str] = mapped_column(String(64), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), index=True)
    entity_id: Mapped[str] = mapped_column(String(128), index=True)

    status: Mapped[SyncJobStatus] = mapped_column(Enum(SyncJobStatus, create_constraint=False), index=True)

    priority: Mapped[JobPriority] = mapped_column(
        Enum(JobPriority, create_constraint=False),
        index=True,
        default=JobPriority.normal,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    max_retries: Mapped[int] = mapped_column(Integer)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)

    payload_version: Mapped[int] = mapped_column(Integer, default=1)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    lease_acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dead_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    dead_error: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    dead_error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)

    is_replay: Mapped[bool] = mapped_column(Boolean, default=False)
    replay_of_job_id: Mapped[int | None] = mapped_column(ForeignKey("sync_jobs.id"), nullable=True, index=True)
    replay_of_attempt_id: Mapped[int | None] = mapped_column(ForeignKey("sync_job_attempts.id"), nullable=True, index=True)

    attempts = relationship(
        "SyncJobAttempt",
        back_populates="job",
        cascade="all, delete-orphan",
        foreign_keys="SyncJobAttempt.job_id",
    )

    replay_of_job = relationship(
        "SyncJob",
        foreign_keys=[replay_of_job_id],
        remote_side="SyncJob.id",
        uselist=False,
    )
    replay_of_attempt = relationship(
        "SyncJobAttempt",
        foreign_keys=[replay_of_attempt_id],
        uselist=False,
    )
