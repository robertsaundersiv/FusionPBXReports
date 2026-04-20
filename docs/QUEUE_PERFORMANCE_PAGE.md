# Queue Performance Page

## Current State

Queue Performance is implemented end-to-end (frontend + backend) using:

- Frontend route: `/queue-performance`
- Backend endpoint: `GET /api/v1/dashboard/queue-performance`

## Filters

- Date range (`start_date`, `end_date`)
- Queue IDs (`queue_ids`)
- Direction input exists, but queue performance is currently enforced to inbound in backend logic
- Timezone
- `strict_answered` toggle

## Response Shape

```json
{
  "queues": [
    {
      "queue_id": "...",
      "queue_name": "...",
      "metrics": {},
      "heatmaps": {},
      "breakdowns": {},
      "hourly": []
    }
  ]
}
```

## Metric Coverage

Per queue metrics include:

- Offered / Answered / Abandoned
- Answer and abandon rates
- ASA avg / p90
- AHT avg / p90
- Service level
- MOS average
- Callback offered/answered
- Repeat caller rate

## Frontend Behavior

- Queue cards are grouped by 3-letter prefix.
- Charts are rendered from `hourly[]` data.
- Shared filter UX is reused across dashboard pages.

## Important Notes

- `GET /api/v1/dashboard/queue-performance/{queue_id}` currently remains a stubbed legacy endpoint.
- The active queue performance UI should rely on `GET /api/v1/dashboard/queue-performance`.
