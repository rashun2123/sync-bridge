from __future__ import annotations

import logging

from fastapi import FastAPI

from app.db.init_db import init_db
from app.jobs.executor import JobExecutor
from app.jobs.handlers.customer_sync import handle_customer_sync
from app.jobs.handlers.invoice_sync import handle_invoice_sync
from app.jobs.registry import JobRegistry
from app.jobs.worker import InProcessWorker
from app.logging.logger import configure_logging
from app.routes.jobs import router as jobs_router
from app.routes.metrics import router as metrics_router
from app.routes.mock import router as mock_router
from app.ui.routes import router as ui_router


def create_app() -> FastAPI:
    configure_logging(level=logging.INFO)
    init_db()

    registry = JobRegistry()
    registry.register("customer_sync", handle_customer_sync, payload_version=1)
    registry.register("invoice_sync", handle_invoice_sync, payload_version=1)

    executor = JobExecutor(registry=registry)
    worker = InProcessWorker(executor=executor)

    app = FastAPI(title="SyncBridge")
    app.include_router(jobs_router)
    app.include_router(metrics_router)
    app.include_router(mock_router)
    app.include_router(ui_router)

    @app.on_event("startup")
    def _startup() -> None:
        worker.start()

    @app.on_event("shutdown")
    def _shutdown() -> None:
        worker.stop()

    return app


app = create_app()
