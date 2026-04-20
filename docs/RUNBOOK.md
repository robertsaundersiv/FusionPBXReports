# Development and Operations Runbook

## Start

```bash
cp .env.example .env
docker compose up -d --build
```

Access app via `https://localhost`.

## Stop / Reset

```bash
docker compose down
docker compose down -v
```

## Logs

```bash
docker compose logs -f
docker compose logs -f backend
docker compose logs -f worker
docker compose logs -f nginx
```

## Backend Tests (Container)

```bash
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from backend-tests
docker compose -f docker-compose.test.yml down -v
```

## Frontend Validation

```bash
cd frontend
npm run lint
npm run build
```

## Production Update

```bash
chmod +x scripts/update-production.sh
./scripts/update-production.sh
```

## Key Operational Notes

- Backend container startup runs migrations and seed/sync scripts.
- Worker startup dispatches metadata, extensions, and ingestion startup tasks.
- Celery beat schedule is configured in `worker/app/tasks/etl.py`.
