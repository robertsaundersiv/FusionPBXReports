# Queue Performance Quick Start

## Page Route

- Frontend route: `/queue-performance`
- API endpoint used by frontend: `GET /api/v1/dashboard/queue-performance`

## What It Shows

Per queue:

- Offered
- Answered
- Abandoned
- Service Level
- ASA
- AHT
- MOS
- Answer Rate
- Hourly trend data

Queues are grouped by first 3 letters in the frontend.

## Test Quickly

1. Start stack:

   ```bash
   docker compose up -d --build
   ```

2. Open app at `https://localhost`.
3. Go to **Queue Performance**.
4. Adjust date range and queue filters.

## API Contract Shape

The response includes:

- `queues[]`
  - `queue_id`
  - `queue_name`
  - `metrics`
  - `hourly[]`

See `docs/QUEUE_PERFORMANCE_PAGE.md` for full details.
