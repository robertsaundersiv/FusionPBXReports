export interface DateRange {
  startDate?: Date;
  endDate?: Date;
  preset: 'today' | 'yesterday' | 'last_7' | 'last_30' | 'custom';
}

export interface DashboardFilters {
  dateRange: DateRange;
  queueIds: string[];
  agentUuids: string[];
  direction?: 'inbound' | 'outbound' | 'local';
  businessHoursOnly: boolean;
  includeOutbound: boolean;
  excludeDeflects: boolean;
  strictQueueAnswered: boolean;
  timezone: string;
}

export interface KPIMetric {
  name: string;
  value: number;
  unit: string;
  formattedValue?: string;
  threshold?: {
    good: number;
    warning: number;
  };
  trend?: number;
  definition: string;
}

export interface TrendDataPoint {
  date: string;
  value: number;
}

export interface CallVolumeBucketPoint {
  bucket: string;
  sortOrder: number;
  totalCalls: number;
  averageCalls: number;
  occurrences: number;
}

export interface CallRecord {
  id: number;
  xml_cdr_uuid: string;
  startTime: string;
  callerIdNumber: string;
  queueName?: string;
  agentName?: string;
  status: string;
  waitTime?: number;
  billsec: number;
  holdTime: number;
  mos?: number;
  hangupCause?: string;
}

export interface Queue {
  id: number;
  queue_id: string;
  name: string;
  description?: string;
  enabled: boolean;
  queue_extension?: string;
  queue_context?: string;
  service_level_threshold: number;
  timezone: string;
  created_at: string;
  updated_at: string;
}

export interface Agent {
  id?: number;
  agent_id?: string | number;
  agent_uuid?: string;
  agent_name: string;
  agent_contact?: string;
  agent_enabled?: boolean;
  created_at?: string;
  updated_at?: string;
}

export type UserRole = 'super_admin' | 'admin' | 'operator';

export interface UserAccount {
  id: number;
  username: string;
  email: string;
  role: UserRole;
  enabled: boolean;
  can_view_unmasked_numbers: boolean;
  created_at: string;
}

export interface ExecutiveOverviewData {
  offered: KPIMetric;
  answerRate: KPIMetric;
  abandonRate: KPIMetric;
  serviceLevel: KPIMetric;
  asa: KPIMetric;
  aht: KPIMetric;
  avgMos: KPIMetric;
  totalTalkTime: KPIMetric;
  
  trends: {
    offered: TrendDataPoint[];
    answered: TrendDataPoint[];
    abandoned: TrendDataPoint[];
    serviceLevel: TrendDataPoint[];
    asa: TrendDataPoint[];
    aht: TrendDataPoint[];
    mos: TrendDataPoint[];
    callVolumeBuckets: {
      byDayOfWeek: CallVolumeBucketPoint[];
      byHourOfDay: CallVolumeBucketPoint[];
    };
  };
  
  rankings: {
    busiestQueues: Array<{ name: string; calls: number }>;
    worstAbandonQueues: Array<{ name: string; rate: number }>;
    worstAsaQueues: Array<{ name: string; asa: number }>;
    lowestMosProviders: Array<{ name: string; mos: number }>;
  };
}

export interface QualityHealthTaskStatus {
  task_name: string;
  display_name: string;
  schedule: string;
  last_executed_at: string | null;
  status: string;
  source: string;
}

export interface QualityHealthData {
  pipeline_status: {
    status: string;
    last_successful_run: string | null;
    last_ingested_insert_date: string | null;
    last_queue_sync: string | null;
    last_agent_sync: string | null;
    last_hourly_agg: string | null;
    last_daily_agg: string | null;
    error_message: string | null;
    error_count: number;
  };
  tasks: QualityHealthTaskStatus[];
}

export interface RunAllQualityHealthTasksResponse {
  message: string;
  chain_id: string;
  tasks: string[];
}

export interface HeatmapDataPoint {
  day: number;  // 0-6 (Mon-Sun)
  hour: number; // 0-23
  value: number;
}

export interface MetricValue {
  value: number;
  unit: string;
}

export interface QueuePerformanceData {
  queueId: string;
  queueName: string;
  metrics: {
    offered: MetricValue;
    answered: MetricValue;
    abandoned: MetricValue;
    answer_rate: MetricValue;
    abandon_rate: MetricValue;
    asa_avg: MetricValue;
    asa_p90: MetricValue;
    aht_avg: MetricValue;
    aht_p90: MetricValue;
    service_level: MetricValue;
    callbacks_offered: MetricValue;
    callbacks_answered: MetricValue;
    repeat_caller_rate: MetricValue;
  };
  heatmaps: {
    offered_by_hour_day: HeatmapDataPoint[];
    abandon_rate_by_hour_day: HeatmapDataPoint[];
    asa_by_hour_day: HeatmapDataPoint[];
  };
  breakdowns: {
    hangup_causes: Array<{ cause: string; count: number; percentage: number }>;
    call_outcomes: Array<{ outcome: string; count: number; percentage: number }>;
  };
}

export interface QueuePerformanceResponse {
  queues: QueuePerformanceData[];
}

export interface RepeatCallerRow {
  caller_id_number: string;
  call_count: number;
  answered_count: number;
  abandoned_count: number;
  queues: string[];
}

export interface RepeatCallersResponse {
  start: string;
  end: string;
  repeat_callers: RepeatCallerRow[];
}

// Hourly time series for queue performance
export interface HourlyMetrics {
  timestamp: string; // ISO timestamp for the hour bucket
  offered: number;
  answered: number;
  abandoned: number;
  service_level: number; // percentage
  asa: number | null; // seconds, null if no answered calls
  aht: number | null; // seconds, null if no answered calls
  mos: number | null; // 0-5, null if no calls with MOS data
}

export interface QueuePerformanceHourlyData {
  queue_id: string;
  queue_name: string;
  metrics: {
    offered: MetricValue;
    answered: MetricValue;
    abandoned: MetricValue;
    answer_rate: MetricValue;
    abandon_rate: MetricValue;
    asa_avg: MetricValue;
    aht_avg: MetricValue;
    service_level: MetricValue;
    mos_avg: MetricValue;
  };
  hourly: HourlyMetrics[]; // Hourly time series
}

export interface QueuePerformanceHourlyResponse {
  queues: QueuePerformanceHourlyData[];
}

// Grouped queue structure for display
export interface GroupedQueue {
  groupKey: string;
  queues: QueuePerformanceHourlyData[];
}

export interface AgentPerformanceData {
  agentUuid: string;
  agentName: string;
  leaderboardPosition: number;
  callsHandled: number;
  avgAht: number;
  avgHold: number;
  avgMos: number;
  missCount: number;
  totalTalkTime: number;
  trends: TrendDataPoint[];
  outliers: CallRecord[];
}

export interface AgentLeaderboardEntry {
  agent_id: string;
  agent_name: string;
  handled_calls: number;
  talk_time_sec: number;
  aht_sec: number;
  hold_avg_sec: number | null;
  mos_avg: number;
  mos_samples: number;
  missed_calls: number;
}

export interface AgentAttributionDiagnostics {
  total_records: number;
  attributed_records: number;
  unknown_records: number;
  unknown_rate_pct: number;
  attribution_sources: {
    cc_agent: number;
    cc_agent_uuid: number;
    extension_uuid: number;
    caller_number: number;
    caller_name_exact: number;
    caller_name_extension: number;
    caller_name_fuzzy: number;
    raw_fallback: number;
  };
}

export interface AgentLeaderboardResponse {
  start: string;
  end: string;
  can_view_missed_calls?: boolean;
  can_view_attribution_diagnostics?: boolean;
  attribution_diagnostics?: AgentAttributionDiagnostics;
  agents: AgentLeaderboardEntry[];
  outbound_added_calls?: number;
}

export interface AgentTrendBucket {
  bucket_start: string;
  handled_calls: number;
  talk_time_sec: number;
  aht_sec: number | null;
  mos_avg: number | null;
  missed_calls: number;
}

export interface AgentTrendsResponse {
  agent_id: string;
  can_view_missed_calls?: boolean;
  buckets: AgentTrendBucket[];
}

export interface AgentOutlierCall {
  call_id: string;
  start_time: string;
  queue?: string | null;
  caller_id?: string | null;
  billsec: number;
  mos?: number | null;
  hangup_cause?: string | null;
}

export interface AgentOutliersResponse {
  agent_id: string;
  type: 'long_calls' | 'low_mos';
  outliers: AgentOutlierCall[];
}

export interface AgentCallRow {
  call_id: string;
  start_time: string;
  queue?: string | null;
  caller_id?: string | null;
  result: 'answered' | 'missed' | 'other';
  talk_time_sec: number;
  aht_sec: number;
  mos?: number | null;
  hangup_cause?: string | null;
}

export interface AgentCallsResponse {
  total: number;
  limit: number;
  offset: number;
  calls: AgentCallRow[];
}

export interface AgentCallDetail {
  call_id: string;
  start_time?: string | null;
  answer_time?: string | null;
  end_time?: string | null;
  direction?: string | null;
  queue?: string | null;
  agent_uuid?: string | null;
  agent?: string | null;
  caller_id_name?: string | null;
  caller_id_number?: string | null;
  destination_number?: string | null;
  duration?: number | null;
  billsec?: number | null;
  hold_accum_seconds?: number | null;
  rtp_audio_in_mos?: number | null;
  hangup_cause?: string | null;
  sip_hangup_disposition?: string | null;
  cc_queue_joined_epoch?: number | null;
  cc_queue_answered_epoch?: number | null;
  cc_queue_terminated_epoch?: number | null;
  cc_queue_canceled_epoch?: number | null;
  cc_cancel_reason?: string | null;
  cc_cause?: string | null;
  cc_agent_type?: string | null;
  cc_agent_bridged?: string | null;
  cc_side?: string | null;
  cc_member_uuid?: string | null;
  bridge_uuid?: string | null;
  leg?: string | null;
  last_app?: string | null;
  call_disposition?: string | null;
}

export interface AgentPerformanceQueueBreakdown {
  handled_calls: number;
  talk_time_sec: number;
  missed_calls: number;
}

export interface AgentPerformanceReportRow {
  agent_id: string;
  agent_name: string;
  handled_calls: number;
  talk_time_sec: number;
  aht_sec: number | null;
  missed_calls: number;
  queues: Record<string, AgentPerformanceQueueBreakdown>;
}

export interface AgentPerformanceReportResponse {
  start: string;
  end: string;
  can_view_missed_calls?: boolean;
  queues: Array<{ queue_id: string; queue_name: string }>;
  agents: AgentPerformanceReportRow[];
}
export interface QueueReportRow {
  queue_id: string;
  queue_name: string;
  offered: number;
  answered: number;
  abandoned: number;
  service_level_30: number;
  asa_sec: number;
  aht_sec: number;
  sl30_numerator: number;
  sl30_denominator: number;
  asa_answered_count: number;
  aht_answered_count: number;
}

export interface QueuePerformanceReportResponse {
  start: string;
  end: string;
  rows: QueueReportRow[];
}

export interface OutboundCallUserRow {
  agent_name: string;
  count: number;
  aht_seconds: number;
}

export interface OutboundCallPrefixRow {
  prefix: string;
  count: number;
  aht_seconds: number;
}

export interface OutboundUnknownLabelRow {
  label: string;
  count: number;
}

export interface OutboundDiagnostics {
  total_records: number;
  attributed_records: number;
  unknown_records: number;
  unknown_rate_pct: number;
  attribution_sources: {
    agent_map: number;
    extension_uuid: number;
    caller_name_exact: number;
    caller_name_extension: number;
    raw_identifier_fallback: number;
  };
  unknown_reasons: {
    missing_all_identifiers: number;
    extension_uuid_unmapped: number;
    unresolved_with_identifiers: number;
  };
  top_unknown_caller_labels: OutboundUnknownLabelRow[];
}

export interface OutboundCallsResponse {
  start: string;
  end: string;
  by_user: OutboundCallUserRow[];
  by_prefix: OutboundCallPrefixRow[];
  diagnostics?: OutboundDiagnostics;
}