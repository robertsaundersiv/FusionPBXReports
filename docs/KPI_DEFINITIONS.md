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
- Voicemail Calls
- Missed Calls
- Missed Percent
- Service Level (30s)
- ASA
- AHT
- MOS
- Callback counts
- Repeat caller rate

Queue calculations use a **deduplicated queue-entry method** (grouping by caller + queue join epoch) to avoid multi-leg overcounting.

Current queue-outcome semantics are:

- `Answered`: queue entry is answered when any leg has `cc_queue_answered_epoch`; in standard mode, a fallback also counts `answer_epoch` + `NORMAL_CLEARING` as answered.
- `Voicemail Calls`: queue entries that were not answered by an agent and match voicemail routing signals such as `last_app = voicemail`, voicemail disposition/agent type/message fields, `last_arg` containing `voicemail`, or FusionPBX voicemail feature-code routing (`destination_number` / `caller_destination` starting with `*99`).
- `Abandoned`: queue entries that were not answered and did not end in voicemail.
- `Abandon Rate`: `abandoned / offered`, excluding voicemail entries from the numerator.
- `Missed Calls`: `abandoned + voicemail`.
- `Missed Percent`: `missed calls / offered`.

The answered fallback intentionally does **not** classify voicemail-routed legs as answered.

## Executive Overview KPI Group

Used by `GET /api/v1/dashboard/executive-overview`:

- Offered
- Answer Rate
- Abandon Rate
- Voicemail Calls
- Missed Calls
- Missed Percent
- Service Level
- ASA
- AHT
- Avg MOS
- Total Talk Time

Executive Overview now uses the same queue-entry classification rules as queue performance for answer/abandon/voicemail/missed metrics.

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

## UI Notes

- Day Comparer consumes Executive Overview KPI data for each selected day.
- Day Comparer displays both raw counts and percent-based rows for abandoned, voicemail, and missed outcomes.
- Day-based comparisons are resolved against the selected timezone day boundary, including UTC mode.

Always treat API endpoint code as source of truth when docs and implementation differ.
