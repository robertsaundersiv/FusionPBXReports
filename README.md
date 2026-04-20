# FusionPBXReports

FusionPBXReports is a Docker-based analytics stack for FusionPBX call-center reporting.
It includes:

- **FastAPI backend** (`backend/`)
- **React + TypeScript frontend** (`frontend/`)
- **Celery worker + beat** (`worker/`)
- **PostgreSQL + Redis + Nginx** (`docker-compose.yml`)

## Current Application Scope

### Frontend Pages

- Executive Overview
- Wallboard
- Queue Performance
- Queue Performance Report
- Agent Performance
- Agent Performance Report
- Outbound Calls
- Repeat Callers
- Settings (admin)
- Quality & Health (super_admin only)

### Backend API Groups

- `/api/v1/auth/*`
- `/api/v1/cdr/*`
- `/api/v1/dashboard/*`
- `/api/v1/agent-performance/*`
- `/api/v1/admin/*`

## Quick Start

```bash
git clone <repository-url>
cd FusionPBXReports
cp .env.example .env
docker compose up -d --build
```

App entry points via Nginx:

- `http://localhost` (redirects to HTTPS)
- `https://localhost`

## Environment Variables

Start from `.env.example` and set at minimum:

- `FUSIONPBX_HOST`
- `FUSIONPBX_API_KEY`
- `DB_PASSWORD`
- `JWT_SECRET`

Additional auth hardening vars are also defined in `.env.example`.

## Testing and Validation

- Backend container tests:

  ```bash
  docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from backend-tests
  docker compose -f docker-compose.test.yml down -v
  ```

- Frontend lint/build (run from `frontend/`):

  ```bash
  npm run lint
  npm run build
  ```

> Note: the current repo has an existing frontend lint error in `Wallboard.tsx` (`no-unsafe-finally`).

## Worker Schedules (Current)

Configured in `worker/app/tasks/etl.py`:

- `sync_extensions`: every 15 minutes
- `ingest_cdr_records`: every 15 minutes
- `cleanup_old_cdr_records`: every 15 minutes
- `sync_metadata`: every 4 hours
- `compute_hourly_aggregates`: every 15 minutes
- `compute_daily_aggregates`: daily at 06:00 UTC

## Additional Documentation

- `docs/RUNBOOK.md` — operational and development commands
- `docs/ARCHITECTURE.md` — system architecture and flow
- `docs/KPI_DEFINITIONS.md` — metric definitions used by the app
- `docs/QUEUE_PERFORMANCE_PAGE.md` — queue performance page + API contract
- `docs/TESTING_ENVIRONMENT.md` — testing workflow
