# Architecture Overview

## Runtime Topology

```text
Browser
  -> Nginx (80/443)
    -> Frontend container
    -> Backend container (FastAPI)
Backend/Worker
  -> PostgreSQL
  -> Redis
Worker
  -> FusionPBX API
```

## Main Components

- **Frontend (`frontend/`)**: React + TypeScript dashboards and reports
- **Backend (`backend/`)**: FastAPI APIs, auth, analytics queries
- **Worker (`worker/`)**: Celery tasks for ingestion/sync/aggregation
- **Nginx (`docker/nginx.conf`)**: TLS termination and routing

## API Surface (Current)

- `/api/v1/auth/*`
- `/api/v1/cdr/*`
- `/api/v1/dashboard/*`
- `/api/v1/agent-performance/*`
- `/api/v1/admin/*`

## Data Flow

1. Worker ingests CDR + metadata from FusionPBX.
2. Data is stored in PostgreSQL.
3. Backend computes/serves dashboard metrics.
4. Frontend queries backend APIs and renders pages.

## Scheduling Model

Canonical beat schedule is defined in `worker/app/tasks/etl.py`.
Current cadence includes 15-minute ingestion/sync jobs, 4-hour metadata sync, and daily aggregates.
