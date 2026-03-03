# KPI Definitions Document

## Single Source of Truth for Call Center Metrics

This document defines all KPIs used in the FusionPBX Analytics Dashboard. These definitions are implemented in `backend/app/kpi_definitions.py` and used consistently across ETL, API, and dashboards.

## Call Classification

Before computing KPIs, calls are classified into categories:

### Answered
- **Definition**: `status = 'answered' OR billsec > 0`
- **Includes**: Calls with agent handling time or confirmed connection
- **Excludes**: Calls that failed before connection

### Offered (Queue)
- **Definition**: `cc_queue_joined_epoch IS NOT NULL`
- **Includes**: Any inbound call offered to a queue
- **Excludes**: Direct agent transfers, internal calls

### Inbound Offered (All)
- **Definition**: `direction = 'inbound'`
- **Includes**: All inbound calls regardless of routing
- **Excludes**: Outbound and local calls

### Abandoned
- **Definition**: `cc_queue_joined_epoch IS NOT NULL AND cc_queue_answered_epoch IS NULL`
- **Includes**: Queue calls without agent pickup before disconnect
- **Excludes**: Calls never offered to queue

### Callback
- **Definition**: `cc_agent_type = 'callback'`
- **Includes**: Agent-initiated callback requests
- **Excludes**: Regular inbound/outbound calls

---

## Volume KPIs

### Total Inbound Calls
- **Name**: Total Inbound Calls
- **Calculation**: COUNT(*) WHERE direction = 'inbound'
- **Unit**: Calls
- **Excludes**: Internal, test calls
- **Scope**: Global or selected queues
- **Use Case**: Understand overall inbound demand

### Total Queue-Offered Calls
- **Name**: Total Queue-Offered Calls
- **Calculation**: COUNT(*) WHERE cc_queue_joined_epoch IS NOT NULL
- **Unit**: Calls
- **Scope**: Per queue or global
- **Use Case**: Queue capacity analysis

### Answered Calls
- **Name**: Answered Calls
- **Calculation**: COUNT(*) WHERE status = 'answered' OR billsec > 0
- **Unit**: Calls
- **Scope**: Per queue, agent, or global
- **Use Case**: Workload baseline

### Abandoned Calls
- **Name**: Abandoned Calls
- **Calculation**: COUNT(*) WHERE cc_queue_joined_epoch IS NOT NULL AND cc_queue_answered_epoch IS NULL
- **Unit**: Calls
- **Scope**: Per queue or global
- **Use Case**: Customer satisfaction indicator

---

## Service Level KPIs

### Answer Rate
- **Name**: Answer Rate
- **Definition**: Percentage of offered calls answered by system
- **Calculation**: (answered_calls / total_queue_offered_calls) × 100
- **Unit**: %
- **Threshold**: Good ≥ 80%, Warning ≥ 70%
- **Scope**: Per queue, time period
- **Business Impact**: Measures operational efficiency and agent availability

### Abandon Rate
- **Name**: Abandon Rate
- **Definition**: Percentage of offered queue calls not answered
- **Calculation**: (abandoned_calls / total_queue_offered_calls) × 100
- **Unit**: %
- **Threshold**: Good ≤ 10%, Warning ≤ 20%
- **Scope**: Per queue, time period
- **Business Impact**: Customer experience and satisfaction metric

### Average Speed of Answer (ASA)
- **Name**: Average Speed of Answer
- **Definition**: Average wait time from queue entry to agent answer
- **Calculation**: AVG(cc_queue_answered_epoch - cc_queue_joined_epoch) WHERE cc_queue_answered_epoch IS NOT NULL
- **Unit**: Seconds
- **Threshold**: Good ≤ 30s, Warning ≤ 60s
- **Scope**: Per queue, per agent, time period
- **Includes**: Only answered queue calls
- **Business Impact**: Measures queue efficiency and customer experience

### Wait Time Average
- **Name**: Average Wait Time
- **Definition**: Average total wait time including answered calls
- **Calculation**: AVG(cc_queue_answered_epoch - cc_queue_joined_epoch) WHERE status = 'answered'
- **Unit**: Seconds
- **Scope**: Per queue, time period

### Wait Time P50 (Median)
- **Name**: Wait Time Median
- **Definition**: 50th percentile wait time (median)
- **Calculation**: PERCENTILE(cc_queue_answered_epoch - cc_queue_joined_epoch, 50)
- **Unit**: Seconds
- **Interpretation**: Half of callers waited less, half waited more

### Wait Time P90
- **Name**: Wait Time P90
- **Definition**: 90th percentile wait time (worst 10%)
- **Calculation**: PERCENTILE(cc_queue_answered_epoch - cc_queue_joined_epoch, 90)
- **Unit**: Seconds
- **Threshold**: Good ≤ 60s, Warning ≤ 120s
- **Interpretation**: Only worst 10% of calls had longer waits

### Service Level %
- **Name**: Service Level Percentage
- **Definition**: % of answered queue calls within threshold time
- **Calculation**: (COUNT(*) WHERE (cc_queue_answered_epoch - cc_queue_joined_epoch) ≤ threshold / total_answered_queue_calls) × 100
- **Unit**: %
- **Default Threshold**: 30 seconds (configurable per queue)
- **Threshold**: Good ≥ 80%, Warning ≥ 70%
- **Scope**: Per queue, time period
- **Business Impact**: Industry standard SLA metric

---

## Handle Time KPIs

### Average Handle Time (AHT)
- **Name**: Average Handle Time
- **Definition**: Average total call duration including talk and hold time
- **Calculation**: AVG(billsec + hold_accum_seconds) WHERE status = 'answered'
- **Unit**: Seconds
- **Threshold**: Good ≤ 300s, Warning ≤ 600s
- **Scope**: Per agent, queue, time period
- **Includes**: Talk time + hold time
- **Excludes**: Abandoned calls, failed calls
- **Business Impact**: Productivity and efficiency metric

### AHT P90
- **Name**: AHT P90
- **Definition**: 90th percentile handle time
- **Calculation**: PERCENTILE(billsec + hold_accum_seconds, 90) WHERE status = 'answered'
- **Unit**: Seconds
- **Interpretation**: Worst 10% of calls

---

## Quality KPIs

### Average MOS (Mean Opinion Score)
- **Name**: Average MOS
- **Definition**: Average voice quality rating
- **Calculation**: AVG(rtp_audio_in_mos) WHERE status = 'answered'
- **Unit**: Score (0-5 scale)
- **Threshold**: Good ≥ 4.0, Warning ≥ 3.8
- **Scope**: Per queue, provider, codec, time period
- **Metric**: rtp_audio_in_mos from RTP statistics
- **Excludes**: Calls with no media
- **Business Impact**: Voice quality and customer satisfaction

### MOS P10 (Percentile 10)
- **Name**: MOS P10
- **Definition**: 10th percentile MOS (worst 10% of calls)
- **Calculation**: PERCENTILE(rtp_audio_in_mos, 10) WHERE status = 'answered'
- **Unit**: Score
- **Interpretation**: Worst voice quality experienced
- **Use Case**: Identify quality issues affecting minorities of calls

### Bad Call Rate
- **Name**: Bad Call Rate
- **Definition**: Percentage of calls with poor voice quality
- **Calculation**: (COUNT(*) WHERE rtp_audio_in_mos < threshold / total_answered_calls) × 100
- **Unit**: %
- **Default Threshold**: 3.8 MOS (configurable)
- **Threshold**: Good ≤ 5%, Warning ≤ 10%
- **Scope**: Per queue, codec, provider, time period
- **Excludes**: Calls with no media
- **Business Impact**: Voice quality baseline

### Codec Distribution
- **Name**: Codec Distribution
- **Definition**: Breakdown of calls by codec pairs
- **Calculation**: GROUP BY read_codec, write_codec; COUNT(*) / total_calls × 100
- **Unit**: %
- **Scope**: Per queue, provider, time period
- **Use Case**: Network optimization and troubleshooting

### Post Dial Delay (PDD) Average
- **Name**: PDD Average
- **Definition**: Average time from dial to first ringing
- **Calculation**: AVG(pdd_ms)
- **Unit**: Milliseconds
- **Threshold**: Good ≤ 200ms, Warning ≤ 500ms
- **Scope**: Per provider, time period
- **Business Impact**: Network performance and call setup quality

---

## Failure Analysis KPIs

### Hangup Cause Distribution
- **Name**: Hangup Cause Distribution
- **Definition**: Breakdown of why calls ended
- **Calculation**: GROUP BY hangup_cause; COUNT(*) / total_calls × 100
- **Unit**: %
- **Common Causes**: Normal Clearing, User Busy, No Answer, etc.
- **Use Case**: Root cause analysis

### Q.850 Code Distribution
- **Name**: Q.850 Code Distribution
- **Definition**: ISDN cause code breakdown
- **Calculation**: GROUP BY hangup_cause_q850; COUNT(*) / total_calls × 100
- **Unit**: %
- **Standard**: ISDN Q.850 standard causes
- **Use Case**: Telecom issue diagnosis

### SIP Disposition Distribution
- **Name**: SIP Disposition Distribution
- **Definition**: SIP-level hangup reasons
- **Calculation**: GROUP BY sip_hangup_disposition; COUNT(*) / total_calls × 100
- **Unit**: %
- **Use Case**: Protocol-level troubleshooting

### Failure Rate
- **Name**: Failure Rate
- **Definition**: Percentage of calls not successfully completed
- **Calculation**: (non_answered_calls / total_calls) × 100
- **Unit**: %
- **Scope**: Per provider, queue, time period
- **Business Impact**: System reliability

---

## Callback KPIs

### Callbacks Offered
- **Name**: Callbacks Offered
- **Definition**: Total callback requests generated
- **Calculation**: COUNT(*) WHERE cc_agent_type = 'callback'
- **Unit**: Calls
- **Scope**: Per agent, queue, time period

### Callbacks Answered
- **Name**: Callbacks Answered
- **Definition**: Callback requests completed
- **Calculation**: COUNT(*) WHERE cc_agent_type = 'callback' AND status = 'answered'
- **Unit**: Calls
- **Scope**: Per agent, queue, time period

### Callback Completion Rate
- **Name**: Callback Completion Rate
- **Definition**: Percentage of callbacks completed
- **Calculation**: (callbacks_answered / callbacks_offered) × 100
- **Unit**: %
- **Threshold**: Good ≥ 90%, Warning ≥ 75%
- **Business Impact**: Alternative to hold time; measures customer satisfaction

---

## Repeat Caller KPIs

### Repeat Caller Rate
- **Name**: Repeat Caller Rate
- **Definition**: % of inbound calls from repeat callers
- **Calculation**: (COUNT(DISTINCT caller_id_number WHERE call_count_in_window > 1) / total_inbound_calls) × 100
- **Unit**: %
- **Default Window**: 24 hours (configurable)
- **Scope**: Per queue, time period
- **Business Impact**: Indicates unresolved issues or system friction

### Repeat After Abandon Rate
- **Name**: Repeat After Abandon Rate
- **Definition**: % of abandoned calls where caller called back within window
- **Calculation**: (COUNT(caller_id_number WHERE previously_abandoned_within_window) / abandoned_calls) × 100
- **Unit**: %
- **Default Window**: 24 hours (configurable)
- **Business Impact**: Measures urgency and satisfaction

### Top Repeat Callers List
- **Name**: Top Repeat Callers
- **Definition**: Ranking of most frequent callers
- **Scope**: Per queue, time period
- **Masking**: Numbers masked for non-admin users
- **Use Case**: Identify problematic customers or system issues

---

## Talk Time KPIs

### Total Talk Time
- **Name**: Total Talk Time
- **Definition**: Sum of all billable seconds
- **Calculation**: SUM(billsec)
- **Unit**: Seconds
- **Scope**: Per agent, queue, time period
- **Use Case**: Workload and capacity planning

### Total Hold Time
- **Name**: Total Hold Time
- **Definition**: Sum of all hold time across calls
- **Calculation**: SUM(hold_accum_seconds)
- **Unit**: Seconds
- **Scope**: Per agent, queue, time period
- **Use Case**: Identify hold issues

---

## Filter Scope & Exclusions

All KPIs support these filters:
- **Date Range**: Today, Yesterday, Last 7, Last 30, Custom
- **Queue(s)**: Single or multi-select
- **Agent(s)**: Single or multi-select
- **Direction**: Inbound, Outbound, Local
- **Business Hours**: Toggle on/off per queue configuration
- **Timezone**: Display timezone (default: America/Phoenix)

### Global Exclusions
- **Internal Calls**: Calls within same domain
- **Test Calls**: Marked explicitly
- **Deleted Records**: Soft-deleted CDR entries
- **No Media**: Calls with rtp_audio_in_mos = NULL for quality metrics

---

## Computation Strategy

### Real-Time vs. Aggregated
- **Real-Time**: Drilldown queries on raw CDR data (detailed, slower)
- **Aggregated**: Pre-computed hourly/daily tables (fast, for dashboards)

### Update Frequency
- **Hourly Aggregates**: Updated every 15 minutes
- **Daily Aggregates**: Updated daily at 2 AM UTC
- **Trends**: Derived from hourly aggregates

### Recalculation Windows
- **Late Insert Handling**: Re-pull 15-minute safety window
- **Late Aggregation**: Re-compute up to 3 hours past
- **Idempotency**: All calculations use UPSERT by natural keys

---

## Dashboard KPI Display

Each KPI widget on dashboards shows:
1. **Current Value** - Primary metric
2. **Trend** - % change vs. previous period
3. **Color Coding** - Green (good) / Yellow (warning) / Red (bad)
4. **Definition Tooltip** - Hover or click for full KPI documentation
5. **Drill-Down** - Click to see underlying call records

---

## Configuration

Thresholds can be customized per queue in Admin Settings:
- Service Level threshold (default: 30s)
- MOS bad call threshold (default: 3.8)
- Repeat caller window (default: 24h)
- Business hours per queue
- Timezone per queue

All changes are immediately reflected in dashboard queries.
