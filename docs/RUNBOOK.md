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

## Production Self-Heal Watchdog

Install and enable a local watchdog that checks nginx, backend, and database every 30 seconds.
If a failure persists for more than 300 seconds, it rebuilds app images, recreates app containers,
and restarts nginx.

```bash
sudo bash ./scripts/install-watchdog.sh
```

Verify timer and recent watchdog activity:

```bash
sudo systemctl status phonereports-watchdog.timer --no-pager
sudo systemctl list-timers --all | grep phonereports-watchdog
sudo journalctl -u phonereports-watchdog.service -n 100 --no-pager
```

Temporarily disable:

```bash
sudo systemctl disable --now phonereports-watchdog.timer
```

## Key Operational Notes

- Backend container startup runs migrations and seed/sync scripts.
- Worker startup dispatches metadata, extensions, and ingestion startup tasks.
- Celery beat schedule is configured in `worker/app/tasks/etl.py`.
