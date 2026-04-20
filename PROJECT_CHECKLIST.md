# Project Checklist (Current Maintenance)

Use this checklist for ongoing maintenance and feature work.

## Documentation

- [ ] Update relevant markdown docs when behavior or contracts change
- [ ] Keep endpoint lists aligned with `backend/app/api/*`
- [ ] Keep frontend page lists aligned with `frontend/src/pages/*`

## Backend

- [ ] Run containerized backend tests before release
- [ ] Verify auth/role assumptions (`super_admin`, `admin`, `operator`)
- [ ] Confirm dashboard and agent-performance endpoint contracts

## Frontend

- [ ] Run `npm run build` from `frontend/`
- [ ] Run `npm run lint` from `frontend/`
- [ ] Validate route/navigation changes in `App.tsx` and `Layout.tsx`

## Worker / Data Pipeline

- [ ] Confirm scheduled jobs in `worker/app/tasks/etl.py`
- [ ] Validate metadata sync and extension sync behavior
- [ ] Check cleanup retention settings before deployment

## Deployment

- [ ] Confirm `.env` values for production
- [ ] Ensure valid certs in `docker/ssl/`
- [ ] Run `scripts/update-production.sh` for production updates
