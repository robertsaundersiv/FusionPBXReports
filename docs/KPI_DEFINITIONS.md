# KPI Definitions (Code-Aligned)

This document summarizes KPI groups used by current dashboard and report endpoints.
Primary implementation logic is in:

- `backend/app/kpi_definitions.py`
- `backend/app/api/dashboard.py`
- `backend/app/api/agent_performance.py`

## Queue KPI Group

Used by queue performance endpoints and UI:

- Offered
- Answered
- Abandoned
- Answer Rate
- Abandon Rate
- Service Level (30s)
- ASA
- AHT
- MOS
- Callback counts
- Repeat caller rate

Queue calculations use a **deduplicated queue-entry method** (grouping by caller + queue join epoch) to avoid multi-leg overcounting.

## Executive Overview KPI Group

Used by `GET /api/v1/dashboard/executive-overview`:

- Offered
- Answer Rate
- Abandon Rate
- Service Level
- ASA
- AHT
- Avg MOS
- Total Talk Time

## Agent Performance KPI Group

Used by `/api/v1/agent-performance/*` endpoints:

- Leaderboard metrics
- Trend metrics
- Outlier metrics
- Call-level drilldown metrics

## Outbound Call KPI Group

Used by `GET /api/v1/dashboard/outbound-calls`:

- Calls and talk time by user
- Calls and talk time by prefix
- Attribution diagnostics

## Filters and Scope

Common filter dimensions used across endpoints:

- Date window
- Queue selection
- Direction (where endpoint supports it)
- Timezone (selected dashboard/report endpoints)

Always treat API endpoint code as source of truth when docs and implementation differ.
