# SyncBridge

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115.6-009688)](https://fastapi.tiangolo.com/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0.36-red)](https://www.sqlalchemy.org/)
[![CI](https://github.com/Siggmond/sync-bridge/actions/workflows/ci.yml/badge.svg)](https://github.com/Siggmond/sync-bridge/actions/workflows/ci.yml)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Made with SQL](https://img.shields.io/badge/queue-database--backed-informational)](#)

SyncBridge is a small, backend-focused project that demonstrates how to build a reliable sync worker without hiding complexity.

It models “do work in the background” as explicit jobs stored in a database:
- you can enqueue work via HTTP
- the worker leases jobs, executes them, and records each attempt
- failures become visible and actionable (retries, DLQ, replay)

The demo integration is intentionally simple: sync data from a mock CRM into a mock Billing system.

## Why this project exists

When you integrate two external systems, the happy path is easy. The hard parts show up later:
- an upstream 503
- rate limiting (429)
- partial failures and retries
- duplicate requests
- a worker crash mid-run

SyncBridge exists to show (in a small codebase) the engineering decisions that make these systems survivable: idempotency, leases, retry policy, and observability.

## What problem it solves (plain language)

SyncBridge is a “job orchestration” layer for integration work:
- **Orchestration**: turn a request (“sync customer c_1001”) into a durable `SyncJob`
- **Retries**: retry retryable failures with exponential backoff
- **Leases**: prevent two workers from doing the same work at the same time, and recover if a worker dies
- **Idempotency**: avoid creating duplicate active jobs for the same `(job_type, entity_id)`

## Who this project is for

- Backend engineers who want a clean reference for job/worker patterns.
- People preparing for system design interviews (leases, retries, DLQ, idempotency).
- Engineers learning FastAPI + SQLAlchemy with a realistic, operational use case.

## What this is NOT

- Not a full distributed queue or streaming system (Kafka, RabbitMQ).
- Not a production task runner like Celery/Sidekiq/Temporal.
- Not a multi-node worker fleet with leader election and sharding.

This project intentionally stays “small but correct” so you can read it end-to-end.

## Key design decisions

### 1) Database is the source of truth
Jobs and attempts are stored in SQL (SQLite by default) using SQLAlchemy.

### 2) Leases for safe claiming
The worker uses `lease_owner` + `lease_expires_at`:
- claiming a job is explicit
- if a worker crashes mid-run, the lease can expire and the job can be reclaimed

### 3) Retries with typed error classification
Errors are classified and stored on the attempt/job:
- `UpstreamTimeout` (retryable)
- `UpstreamRateLimited` (retryable)
- `NotFound` (non-retry)
- `ValidationError` (non-retry)

Retryable failures get exponential backoff (`base * 2^(attempt-1)`).

### 4) Dead-letter queue (DLQ)
If a retryable failure exceeds `max_retries`, the job is marked `dead` and a final error snapshot is stored.

### 5) Replay creates a new job
Replay does not “mutate history”. It creates a new job linked to the failed job/attempt (`replay_of_job_id`, `replay_of_attempt_id`).

### 6) UTC-aware time handling
All internal timestamps are normalized to UTC-aware datetimes.

### 7) Correlation IDs for tracing
Each job has a `correlation_id` propagated to integration clients via `X-Correlation-ID`.

## Architecture (where to look)

- `app/routes/` HTTP API for enqueueing and inspecting jobs
- `app/services/` job creation and control operations (retry/cancel/replay)
- `app/jobs/` worker loop + executor + job registry
- `app/models/` SQLAlchemy models (`SyncJob`, `SyncJobAttempt`)
- `app/integrations/` external client wrappers + typed external errors
- `app/ui/` minimal server-rendered admin UI (Jinja2)
- `app/logging/` structured JSON logs

## Screenshots

> All screenshots are from a live local run.

### 01-api-docs.png
FastAPI OpenAPI docs showing job, control, and metrics endpoints.

### 02-enqueue-job-response.png
Enqueueing a job via HTTP and receiving a durable job record.

### 03-ui-job-list.png
Admin UI showing multiple jobs with different states.

### 04-ui-job-detail-attempts.png
Single job detail page with full attempt history and error types.

### 05-retryable-failure-logs.png
Terminal logs showing retryable failures and retries.

### 06-backoff-next-run.png
Job scheduled with future `next_run_at` after a failure.

### 07-dlq-dead-job.png
Job marked `dead` after exceeding retry budget.

### 08-cancel-job.png
Canceling a pending or running job via control endpoint.

### 09-replay-creates-new-job.png
Replay operation creating a new job linked to the failed one.

### 10-metrics-endpoint.png
Metrics endpoint returning job counts and success rate.

## Quickstart

### Prerequisites
- Python 3.10+
- pip

### 1) Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

### 3) Run the service

```bash
uvicorn app.main:app --reload
```

Open:
- Admin UI: http://127.0.0.1:8000/ui/jobs
- API docs: http://127.0.0.1:8000/docs

## Using the demo

### Enqueue jobs

```bash
curl -X POST http://127.0.0.1:8000/api/jobs/customer \
  -H "Content-Type: application/json" \
  -d '{"entity_id":"c_1001"}'
```

### Trigger realistic failures
- `c_flaky` → intermittent 503
- `c_1002` → billing rate limit (429)

## Controls

- `POST /api/jobs/{id}/cancel`
- `POST /api/jobs/{id}/retry`
- `POST /api/jobs/{id}/replay`

## Metrics

`GET /metrics` returns job counts, retry stats, and average duration.

## Notes

- The database is the queue.
- The worker is intentionally in-process.
- The goal is correctness and clarity.

---

If you’re reading this and have feedback, questions, or ideas for improvement, feel free to open an issue.

This project was built with an emphasis on correctness, reliability, and real-world failure handling.
