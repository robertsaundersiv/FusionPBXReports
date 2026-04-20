# Testing Environment

## Backend (Preferred)

Run backend tests in production-like containers:

```bash
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from backend-tests
docker compose -f docker-compose.test.yml down -v
```

## Backend (Local Python Environment)

If your local environment is prepared with dependencies:

```bash
pytest backend/tests -q
```

## Frontend Checks

From `frontend/`:

```bash
npm run lint
npm run build
```

Current known baseline issue: `npm run lint` fails on `frontend/src/pages/Wallboard.tsx` with `no-unsafe-finally`.

## Recommended Workflow

1. Run frontend build/lint checks.
2. Run containerized backend tests.
3. Validate target UI flow in `https://localhost`.
