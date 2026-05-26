# Production Rollback Guide

## Deployment Record

- Deployment date (UTC): 2026-05-26
- Environment: production (`/opt/phonereports`)
- Previous production commit: `6decdd26b2ec745df6ad6bbf4f83e45fcd6ae2c9`
- Deployed commit: `ce779b61f147f09a40ba251f63c74d8430e26a3b`
- Branch deployed: `main`

## Verify Current Version on Server

Run from `/opt/phonereports`:

```bash
sudo git rev-parse HEAD
sudo git log -1 --pretty=format:'%h %ci %s'; echo
sudo docker compose ps
```

Expected commit after this deployment:

```text
ce779b61f147f09a40ba251f63c74d8430e26a3b
```

## Rollback to Previous Production Commit

Run from `/opt/phonereports`:

```bash
# 1) Move code back to known-good commit
sudo git fetch origin
sudo git checkout 6decdd26b2ec745df6ad6bbf4f83e45fcd6ae2c9

# 2) Rebuild and restart services
sudo docker compose build --no-cache backend frontend worker celery-beat
sudo docker compose up -d backend frontend worker celery-beat

# 3) Refresh nginx upstream resolution after backend recreation
sudo docker compose restart nginx

# 4) Confirm health
sudo docker compose ps
```

## Roll Forward Again (Return to Latest Main)

```bash
cd /opt/phonereports
sudo bash ./scripts/update-production.sh main
sudo docker compose restart nginx
sudo git rev-parse HEAD
```

## Notes from 2026-05-26 Deploy

- `update-production.sh main` completed and deployed commit `ce779b6`.
- API calls through nginx initially returned `502` due to stale upstream backend container IP after backend recreation.
- Restarting nginx (`sudo docker compose restart nginx`) resolved upstream connection errors.
- 30-day queue report request still showed high backend processing time; test requests were client-canceled at:
  - `rt=27.083s` (HTTP 499)
  - `rt=73.364s` (HTTP 499)
