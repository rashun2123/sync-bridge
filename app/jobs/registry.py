from __future__ import annotations

from collections.abc import Callable

from app.jobs.types import JobContext


JobHandler = Callable[[JobContext], None]


class JobRegistry:
    def __init__(self) -> None:
        self._handlers: dict[tuple[str, int], JobHandler] = {}

    def register(self, job_type: str, handler: JobHandler, *, payload_version: int = 1) -> None:
        self._handlers[(job_type, payload_version)] = handler

    def get(self, job_type: str, *, payload_version: int) -> JobHandler:
        handler = self._handlers.get((job_type, payload_version))
        if handler is None:
            raise KeyError(f"unknown job_type: {job_type} (payload_version={payload_version})")
        return handler
