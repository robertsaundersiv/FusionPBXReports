import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { Search, ChevronLeft, ChevronRight, ChevronUp, ChevronDown } from 'lucide-react';
import { useFilterStore } from '../hooks/useFilterStore';
import DashboardFilterBar from '../components/DashboardFilterBar';
import { dashboardService } from '../services/dashboard';
import { agentPerformanceService } from '../services/agentPerformance';
import { generateHourlyTimeline } from '../utils/queuePerformance';
import type {
  AgentLeaderboardEntry,
  AgentLeaderboardResponse,
  AgentTrendsResponse,
  AgentOutliersResponse,
  AgentCallsResponse,
  AgentCallDetail,
  AgentTrendBucket,
  Queue,
  Agent,
} from '../types';

type TrendMetric = 'handled_calls' | 'talk_time_sec' | 'aht_sec' | 'mos_avg' | 'missed_calls';

const trendMetricLabels: Record<TrendMetric, string> = {
  handled_calls: 'Calls Handled',
  talk_time_sec: 'Talk Time',
  aht_sec: 'AHT',
  mos_avg: 'MOS Avg',
  missed_calls: 'Missed Calls',
};

const trendMetricUnits: Record<TrendMetric, string> = {
  handled_calls: 'calls',
  talk_time_sec: 'sec',
  aht_sec: 'sec',
  mos_avg: 'MOS',
  missed_calls: 'calls',
};

const formatSecondsToHms = (seconds: number): string => {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = Math.floor(seconds % 60);
  return `${hrs.toString().padStart(2, '0')}:${mins.toString().padStart(2, '0')}:${secs
    .toString()
    .padStart(2, '0')}`;
};

const formatSecondsToMmSs = (seconds: number | null): string => {
  if (seconds === null || seconds === undefined) {
    return 'N/A';
  }
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const formatCsvValue = (value: string | number | null | undefined): string => {
  if (value === null || value === undefined) {
    return '';
  }
  const stringValue = String(value);
  const needsQuotes = /[",\n]/.test(stringValue);
  const escaped = stringValue.replace(/"/g, '""');
  return needsQuotes ? `"${escaped}"` : escaped;
};

const formatSearchParams = (filters: any) => {
  const params = new URLSearchParams();
  if (filters.dateRange?.startDate) {
    params.set('start', new Date(filters.dateRange.startDate).toISOString());
  }
  if (filters.dateRange?.endDate) {
    params.set('end', new Date(filters.dateRange.endDate).toISOString());
  }
  if (filters.queueIds?.length) {
    params.set('queues', filters.queueIds.join(','));
  }
  if (filters.agentUuids?.length) {
    params.set('agents', filters.agentUuids.join(','));
  }
  params.set('include_outbound', String(filters.includeOutbound));
  params.set('exclude_deflects', String(filters.excludeDeflects));
  return params;
};

const fillMissingAgentBuckets = (
  buckets: AgentTrendBucket[],
  startDate?: Date,
  endDate?: Date
): AgentTrendBucket[] => {
  if (!startDate || !endDate) {
    return buckets;
  }
  const timeline = generateHourlyTimeline(startDate, endDate);
  const bucketMap = new Map<string, AgentTrendBucket>();
  buckets.forEach((bucket) => {
    const normalized = new Date(bucket.bucket_start);
    normalized.setMinutes(0, 0, 0);
    bucketMap.set(normalized.toISOString(), bucket);
  });

  return timeline.map((timestamp) =>
    bucketMap.get(timestamp) || {
      bucket_start: timestamp,
      handled_calls: 0,
      talk_time_sec: 0,
      aht_sec: null,
      mos_avg: null,
      missed_calls: 0,
    }
  );
};

export default function AgentPerformance() {
  const { agentId } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const initializedRef = useRef(false);
  const agentSyncRef = useRef(false);

  const {
    filters,
    updateDateRange,
    updateQueueIds,
    updateAgentUuids,
    updateIncludeOutbound,
    updateExcludeDeflects,
  } = useFilterStore();

  const [queues, setQueues] = useState<Queue[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [leaderboard, setLeaderboard] = useState<AgentLeaderboardResponse | null>(null);
  const [trends, setTrends] = useState<AgentTrendsResponse | null>(null);
  const [outliersLong, setOutliersLong] = useState<AgentOutliersResponse | null>(null);
  const [outliersLow, setOutliersLow] = useState<AgentOutliersResponse | null>(null);
  const [callsData, setCallsData] = useState<AgentCallsResponse | null>(null);
  const [callDetail, setCallDetail] = useState<AgentCallDetail | null>(null);
  const [selectedMetric, setSelectedMetric] = useState<TrendMetric>('handled_calls');
  const [canViewMissedCalls, setCanViewMissedCalls] = useState(false);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [sortField, setSortField] = useState<keyof AgentLeaderboardEntry>('handled_calls');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [callSearch, setCallSearch] = useState('');
  const [hangupCauseFilter, setHangupCauseFilter] = useState('');
  const [missedOnly, setMissedOnly] = useState(false);
  const [callPage, setCallPage] = useState(1);
  const callLimit = 25;

  const isDetailView = Boolean(agentId);

  useEffect(() => {
    const loadMetadata = async () => {
      try {
        const [queuesData, agentsData] = await Promise.all([
          dashboardService.getQueues(),
          dashboardService.getAgents(),
        ]);
        setQueues(queuesData);
        setAgents(agentsData);
      } catch (error) {
        console.error('Error loading metadata:', error);
      }
    };

    loadMetadata();
  }, []);

  useEffect(() => {
    if (initializedRef.current) {
      return;
    }

    const start = searchParams.get('start');
    const end = searchParams.get('end');
    const queuesParam = searchParams.get('queues');
    const agentsParam = searchParams.get('agents');
    const includeOutbound = searchParams.get('include_outbound');
    const excludeDeflects = searchParams.get('exclude_deflects');

    if (start && end) {
      const startDate = new Date(start);
      const endDate = new Date(end);
      if (!isNaN(startDate.getTime()) && !isNaN(endDate.getTime())) {
        updateDateRange({ preset: 'custom', startDate, endDate });
      }
    }

    if (queuesParam) {
      updateQueueIds(queuesParam.split(',').filter(Boolean));
    }
    if (agentsParam) {
      updateAgentUuids(agentsParam.split(',').filter(Boolean));
    }
    if (includeOutbound !== null) {
      updateIncludeOutbound(includeOutbound === 'true');
    }
    if (excludeDeflects !== null) {
      updateExcludeDeflects(excludeDeflects === 'true');
    }

    initializedRef.current = true;
  }, [searchParams, updateDateRange, updateQueueIds, updateAgentUuids, updateIncludeOutbound, updateExcludeDeflects]);

  useEffect(() => {
    if (!initializedRef.current) {
      return;
    }
    const params = formatSearchParams(filters);
    setSearchParams(params, { replace: true });
  }, [filters, setSearchParams]);

  useEffect(() => {
    if (!agentId || agentSyncRef.current || filters.agentUuids.length > 0) {
      return;
    }
    updateAgentUuids([agentId]);
    agentSyncRef.current = true;
  }, [agentId, filters.agentUuids.length, updateAgentUuids]);

  useEffect(() => {
    const loadLeaderboard = async () => {
      setLoading(true);
      try {
        const leaderboardResponse = await agentPerformanceService.getLeaderboard(filters);
        setLeaderboard(leaderboardResponse);
        setCanViewMissedCalls(Boolean(leaderboardResponse.can_view_missed_calls));
      } catch (error) {
        console.error('Error loading leaderboard:', error);
      } finally {
        setLoading(false);
      }
    };

    loadLeaderboard();
  }, [filters]);

  useEffect(() => {
    if (!isDetailView || !agentId) {
      return;
    }

    const loadDetail = async () => {
      setDetailLoading(true);
      try {
        const [trendResponse, longOutliers, lowOutliers] = await Promise.all([
          agentPerformanceService.getTrends(filters, agentId),
          agentPerformanceService.getOutliers(filters, agentId, 'long_calls', 25),
          agentPerformanceService.getOutliers(filters, agentId, 'low_mos', 25),
        ]);
        setTrends(trendResponse);
        if (trendResponse.can_view_missed_calls !== undefined) {
          setCanViewMissedCalls(Boolean(trendResponse.can_view_missed_calls));
        }
        setOutliersLong(longOutliers);
        setOutliersLow(lowOutliers);
      } catch (error) {
        console.error('Error loading agent detail data:', error);
      } finally {
        setDetailLoading(false);
      }
    };

    loadDetail();
  }, [filters, agentId, isDetailView]);

  useEffect(() => {
    if (!canViewMissedCalls && selectedMetric === 'missed_calls') {
      setSelectedMetric('handled_calls');
    }
    if (!canViewMissedCalls && missedOnly) {
      setMissedOnly(false);
    }
  }, [canViewMissedCalls, selectedMetric, missedOnly]);

  useEffect(() => {
    if (!isDetailView) {
      return;
    }
    setCallPage(1);
  }, [filters, agentId, isDetailView]);

  useEffect(() => {
    if (!isDetailView || !agentId) {
      return;
    }

    const loadCalls = async () => {
      try {
        const response = await agentPerformanceService.getCalls(filters, agentId, {
          limit: callLimit,
          offset: (callPage - 1) * callLimit,
          sort: 'start_epoch',
          order: 'desc',
          search: callSearch || undefined,
          hangupCause: hangupCauseFilter || undefined,
          missedOnly,
        });
        setCallsData(response);
      } catch (error) {
        console.error('Error loading calls:', error);
      }
    };

    loadCalls();
  }, [filters, agentId, isDetailView, callPage, callSearch, hangupCauseFilter, missedOnly]);

  const handleFiltersChange = (newFilters: typeof filters) => {
    updateDateRange(newFilters.dateRange);
    updateQueueIds(newFilters.queueIds);
    updateAgentUuids(newFilters.agentUuids);
    updateIncludeOutbound(newFilters.includeOutbound);
    updateExcludeDeflects(newFilters.excludeDeflects);

    if (newFilters.agentUuids.length === 1) {
      const selectedAgent = newFilters.agentUuids[0];
      if (selectedAgent && selectedAgent !== agentId) {
        navigate(`/agent-performance/${selectedAgent}`);
      }
    } else if (agentId) {
      navigate('/agent-performance');
    }
  };

  const sortedAgents = useMemo(() => {
    if (!leaderboard?.agents) {
      return [];
    }
    const sorted = [...leaderboard.agents].sort((a, b) => {
      const valueA = a[sortField] ?? 0;
      const valueB = b[sortField] ?? 0;
      if (valueA < valueB) {
        return sortDirection === 'asc' ? -1 : 1;
      }
      if (valueA > valueB) {
        return sortDirection === 'asc' ? 1 : -1;
      }
      return 0;
    });
    return sorted;
  }, [leaderboard, sortField, sortDirection]);

  const selectedAgent = useMemo(() => {
    if (!leaderboard || !agentId) {
      return null;
    }
    return (
      leaderboard.agents.find((agent) => String(agent.agent_id) === String(agentId)) ||
      null
    );
  }, [leaderboard, agentId]);

  const selectedAgentName = useMemo(() => {
    if (!agentId) {
      return null;
    }

    // First try to get name from leaderboard (includes performance data)
    const leaderboardAgent = leaderboard?.agents.find((agent) => String(agent.agent_id) === String(agentId));
    if (leaderboardAgent) {
      return leaderboardAgent.agent_name;
    }

    // Fall back to agents list (metadata)
    const agentMetadata = agents.find(
      (agent) => String(agent.agent_uuid ?? agent.agent_id ?? agent.id) === String(agentId)
    );
    return agentMetadata?.agent_name || agentId;
  }, [agentId, leaderboard, agents]);

  const filledBuckets = useMemo(() => {
    if (!trends?.buckets) {
      return [];
    }
    return fillMissingAgentBuckets(
      trends.buckets,
      filters.dateRange.startDate,
      filters.dateRange.endDate
    );
  }, [trends, filters.dateRange.startDate, filters.dateRange.endDate]);

  const chartData = useMemo(() => {
    return filledBuckets.map((bucket) => ({
      bucket_start: bucket.bucket_start,
      value: bucket[selectedMetric] ?? null,
    }));
  }, [filledBuckets, selectedMetric]);

  const visibleTrendMetrics = useMemo(() => {
    const metrics: TrendMetric[] = ['handled_calls', 'talk_time_sec', 'aht_sec', 'mos_avg'];
    if (canViewMissedCalls) {
      metrics.push('missed_calls');
    }
    return metrics;
  }, [canViewMissedCalls]);

  const exportLeaderboardCsv = () => {
    if (!leaderboard?.agents?.length) {
      return;
    }

    const startLabel = filters.dateRange.startDate
      ? filters.dateRange.startDate.toISOString()
      : 'N/A';
    const endLabel = filters.dateRange.endDate
      ? filters.dateRange.endDate.toISOString()
      : 'N/A';

    const lines: string[] = [];
    lines.push(
      `Agent Performance Leaderboard,Start: ${startLabel},End: ${endLabel},Generated: ${new Date().toISOString()}`
    );
    lines.push('');

    const header = [
      'Agent',
      'Calls Handled',
      'Talk Time (sec)',
      'AHT (sec)',
      'MOS Avg',
      'MOS Samples',
    ];

    if (canViewMissedCalls) {
      header.push('Missed Calls');
    }

    lines.push(header.map((column) => `"${column}"`).join(','));

    const rows = sortedAgents.map((agent) => {
      const row: Array<string | number> = [
        agent.agent_name,
        agent.handled_calls,
        agent.talk_time_sec,
        agent.aht_sec ?? '',
        agent.mos_avg ?? '',
        agent.mos_samples ?? '',
      ];
      if (canViewMissedCalls) {
        row.push(agent.missed_calls);
      }
      return row;
    });

    rows.forEach((row) => {
      lines.push(row.map(formatCsvValue).join(','));
    });

    const csv = lines.join('\n');

    const startFileLabel = filters.dateRange.startDate
      ? filters.dateRange.startDate.toISOString().slice(0, 10)
      : 'start';
    const endFileLabel = filters.dateRange.endDate
      ? filters.dateRange.endDate.toISOString().slice(0, 10)
      : 'end';
    const filename = `agent_performance_leaderboard_${startFileLabel}_to_${endFileLabel}.csv`;

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  };

  const handleSort = (field: keyof AgentLeaderboardEntry) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('desc');
    }
  };

  const SortIndicator = ({ field }: { field: keyof AgentLeaderboardEntry }) => {
    if (sortField !== field) return null;
    return sortDirection === 'asc' ? (
      <ChevronUp className="inline ml-1" size={14} />
    ) : (
      <ChevronDown className="inline ml-1" size={14} />
    );
  };

  const openCallDetail = async (callId: string) => {
    try {
      const detail = await agentPerformanceService.getCallDetail(callId);
      setCallDetail(detail);
    } catch (error) {
      console.error('Error loading call detail:', error);
    }
  };

  const closeCallDetail = () => setCallDetail(null);

  if (loading && !leaderboard) {
    return <div className="p-8 text-center">Loading Agent Performance...</div>;
  }

  return (
    <div className="overflow-auto">
      <DashboardFilterBar
        filters={filters}
        queues={queues}
        agents={agents.filter(
          (a): a is Agent & { agent_uuid?: string; agent_id?: string | number } =>
            Boolean(a.agent_uuid) || a.agent_id !== undefined
        )}
        onFiltersChange={handleFiltersChange}
        showAgents={true}
        showDirection={false}
        showOutboundToggle={true}
        showExcludeDeflectsToggle={true}
      />

      <div className="p-6 space-y-6">
        {!isDetailView && (
          <>
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-bold text-gray-900">Agent Performance</h1>
                <p className="text-sm text-gray-500 mt-1">Leaderboard and coaching insights</p>
              </div>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={exportLeaderboardCsv}
                  className="text-sm px-3 py-1.5 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
                  disabled={!leaderboard?.agents?.length}
                >
                  Export CSV
                </button>
                <div className="text-sm text-gray-500">
                  {filters.dateRange.startDate?.toLocaleDateString()} -{' '}
                  {filters.dateRange.endDate?.toLocaleDateString()}
                </div>
              </div>
            </div>

            <div className="card overflow-hidden">
              <table className="min-w-full text-sm">
                <thead className="bg-gray-50 text-gray-700">
                  <tr>
                    <th className="px-4 py-3 text-left cursor-pointer hover:bg-gray-100" onClick={() => handleSort('agent_name')}>
                      Agent <SortIndicator field="agent_name" />
                    </th>
                    <th className="px-4 py-3 text-right cursor-pointer hover:bg-gray-100" onClick={() => handleSort('handled_calls')}>
                      Calls Handled <SortIndicator field="handled_calls" />
                    </th>
                    <th className="px-4 py-3 text-right cursor-pointer hover:bg-gray-100" onClick={() => handleSort('talk_time_sec')}>
                      Talk Time <SortIndicator field="talk_time_sec" />
                    </th>
                    <th className="px-4 py-3 text-right cursor-pointer hover:bg-gray-100" onClick={() => handleSort('aht_sec')}>
                      AHT <SortIndicator field="aht_sec" />
                    </th>
                    <th className="px-4 py-3 text-right cursor-pointer hover:bg-gray-100" onClick={() => handleSort('mos_avg')}>
                      MOS Avg <SortIndicator field="mos_avg" />
                    </th>
                    {canViewMissedCalls ? (
                      <th className="px-4 py-3 text-right cursor-pointer hover:bg-gray-100" onClick={() => handleSort('missed_calls')}>
                        Miss / No-answer <SortIndicator field="missed_calls" />
                      </th>
                    ) : null}
                  </tr>
                </thead>
                <tbody>
                  {sortedAgents.map((agent) => (
                    <tr
                      key={agent.agent_id}
                      className="border-t hover:bg-blue-50 cursor-pointer"
                      onClick={() => navigate(`/agent-performance/${agent.agent_id}`)}
                    >
                      <td className="px-4 py-3 font-medium text-gray-900">{agent.agent_name}</td>
                      <td className="px-4 py-3 text-right">{agent.handled_calls}</td>
                      <td className="px-4 py-3 text-right">{formatSecondsToHms(agent.talk_time_sec)}</td>
                      <td className="px-4 py-3 text-right">{formatSecondsToMmSs(agent.aht_sec)}</td>
                      <td className="px-4 py-3 text-right">
                        {agent.mos_samples > 0 ? `${agent.mos_avg.toFixed(2)} (${agent.mos_samples})` : 'N/A'}
                      </td>
                      {canViewMissedCalls ? <td className="px-4 py-3 text-right">{agent.missed_calls}</td> : null}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}

        {isDetailView && (
          <>
            <div className="flex items-center justify-between">
              <div>
                <button
                  onClick={() => navigate('/agent-performance')}
                  className="text-sm text-blue-600 hover:text-blue-800"
                >
                  Back to leaderboard
                </button>
                <h1 className="text-3xl font-bold text-gray-900 mt-2">
                  {selectedAgentName}
                </h1>
                <p className="text-sm text-gray-500 mt-1">
                  {filters.dateRange.startDate?.toLocaleDateString()} -{' '}
                  {filters.dateRange.endDate?.toLocaleDateString()}
                </p>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 xl:grid-cols-6 gap-4">
              <div className="kpi-card">
                <p className="text-sm text-gray-600">Handled Calls</p>
                <p className="text-2xl font-bold text-gray-900">{selectedAgent?.handled_calls ?? 0}</p>
              </div>
              <div className="kpi-card">
                <p className="text-sm text-gray-600">AHT</p>
                <p className="text-2xl font-bold text-gray-900">
                  {formatSecondsToMmSs(selectedAgent?.aht_sec ?? 0)}
                </p>
              </div>
              <div className="kpi-card">
                <p className="text-sm text-gray-600">Talk Time</p>
                <p className="text-2xl font-bold text-gray-900">
                  {formatSecondsToHms(selectedAgent?.talk_time_sec ?? 0)}
                </p>
              </div>
              <div className="kpi-card">
                <p className="text-sm text-gray-600">MOS Avg</p>
                <p className="text-2xl font-bold text-gray-900">
                  {selectedAgent?.mos_samples ? selectedAgent.mos_avg.toFixed(2) : 'N/A'}
                </p>
                {selectedAgent?.mos_samples ? (
                  <p className="text-xs text-gray-400 mt-1">Samples: {selectedAgent.mos_samples}</p>
                ) : null}
              </div>
              {canViewMissedCalls ? (
                <div className="kpi-card">
                  <p className="text-sm text-gray-600">Missed Calls</p>
                  <p className="text-2xl font-bold text-gray-900">{selectedAgent?.missed_calls ?? 0}</p>
                </div>
              ) : null}
            </div>

            <div className="card space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold">Trends (Hourly)</h3>
                <select
                  className="border border-gray-300 rounded-md px-3 py-1 text-sm"
                  value={selectedMetric}
                  onChange={(e) => setSelectedMetric(e.target.value as TrendMetric)}
                >
                  {visibleTrendMetrics.map((metric) => (
                    <option key={metric} value={metric}>
                      {trendMetricLabels[metric]}
                    </option>
                  ))}
                </select>
              </div>
              {detailLoading ? (
                <p className="text-sm text-gray-500">Loading trends...</p>
              ) : (
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="bucket_start"
                      tickFormatter={(value) => new Date(value).toLocaleString()}
                    />
                    <YAxis />
                    <Tooltip
                      labelFormatter={(value) => new Date(value).toLocaleString()}
                      formatter={(value: any) => [value, trendMetricUnits[selectedMetric]]}
                    />
                    <Line type="monotone" dataKey="value" stroke="#2563eb" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>

            <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
              <div className="card">
                <h3 className="text-lg font-semibold mb-4">Long Calls</h3>
                <table className="min-w-full text-sm">
                  <thead className="text-gray-500">
                    <tr>
                      <th className="text-left py-2">Start</th>
                      <th className="text-left py-2">Queue</th>
                      <th className="text-left py-2">Caller</th>
                      <th className="text-right py-2">Duration</th>
                    </tr>
                  </thead>
                  <tbody>
                    {outliersLong?.outliers.map((call) => (
                      <tr
                        key={call.call_id}
                        className="border-t hover:bg-blue-50 cursor-pointer"
                        onClick={() => openCallDetail(call.call_id)}
                      >
                        <td className="py-2">{new Date(call.start_time).toLocaleString()}</td>
                        <td className="py-2">{call.queue || '—'}</td>
                        <td className="py-2">{call.caller_id || '—'}</td>
                        <td className="py-2 text-right">{formatSecondsToMmSs(call.billsec)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="card">
                <h3 className="text-lg font-semibold mb-4">Low MOS Calls</h3>
                <table className="min-w-full text-sm">
                  <thead className="text-gray-500">
                    <tr>
                      <th className="text-left py-2">Start</th>
                      <th className="text-left py-2">Queue</th>
                      <th className="text-left py-2">Caller</th>
                      <th className="text-right py-2">MOS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {outliersLow?.outliers.map((call) => (
                      <tr
                        key={call.call_id}
                        className="border-t hover:bg-blue-50 cursor-pointer"
                        onClick={() => openCallDetail(call.call_id)}
                      >
                        <td className="py-2">{new Date(call.start_time).toLocaleString()}</td>
                        <td className="py-2">{call.queue || '—'}</td>
                        <td className="py-2">{call.caller_id || '—'}</td>
                        <td className="py-2 text-right">{call.mos?.toFixed(2) ?? 'N/A'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="card space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-4">
                <h3 className="text-lg font-semibold">Calls</h3>
                <div className="flex flex-wrap items-center gap-3">
                  <div className="relative">
                    <Search className="absolute left-3 top-2.5 text-gray-400" size={16} />
                    <input
                      type="text"
                      placeholder="Search caller ID"
                      value={callSearch}
                      onChange={(e) => {
                        setCallSearch(e.target.value);
                        setCallPage(1);
                      }}
                      className="pl-9 pr-3 py-2 border border-gray-300 rounded-md text-sm"
                    />
                  </div>
                  <input
                    type="text"
                    placeholder="Hangup cause"
                    value={hangupCauseFilter}
                    onChange={(e) => {
                      setHangupCauseFilter(e.target.value);
                      setCallPage(1);
                    }}
                    className="px-3 py-2 border border-gray-300 rounded-md text-sm"
                  />
                  {canViewMissedCalls ? (
                    <label className="flex items-center gap-2 text-sm text-gray-700">
                      <input
                        type="checkbox"
                        checked={missedOnly}
                        onChange={(e) => {
                          setMissedOnly(e.target.checked);
                          setCallPage(1);
                        }}
                      />
                      Missed only
                    </label>
                  ) : null}
                </div>
              </div>

              <div className="overflow-auto">
                <table className="min-w-full text-sm">
                  <thead className="text-gray-500">
                    <tr>
                      <th className="text-left py-2">Start</th>
                      <th className="text-left py-2">Queue</th>
                      <th className="text-left py-2">Caller</th>
                      <th className="text-left py-2">Result</th>
                      <th className="text-right py-2">Talk Time</th>
                      <th className="text-right py-2">AHT</th>
                      <th className="text-right py-2">MOS</th>
                      <th className="text-left py-2">Hangup Cause</th>
                    </tr>
                  </thead>
                  <tbody>
                    {callsData?.calls.map((call) => (
                      <tr
                        key={call.call_id}
                        className="border-t hover:bg-blue-50 cursor-pointer"
                        onClick={() => openCallDetail(call.call_id)}
                      >
                        <td className="py-2">{new Date(call.start_time).toLocaleString()}</td>
                        <td className="py-2">{call.queue || '—'}</td>
                        <td className="py-2">{call.caller_id || '—'}</td>
                        <td className="py-2 capitalize">{call.result}</td>
                        <td className="py-2 text-right">{formatSecondsToMmSs(call.talk_time_sec)}</td>
                        <td className="py-2 text-right">{formatSecondsToMmSs(call.aht_sec)}</td>
                        <td className="py-2 text-right">{call.mos?.toFixed(2) ?? 'N/A'}</td>
                        <td className="py-2">{call.hangup_cause || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <div className="flex items-center justify-between text-sm text-gray-600">
                <span>
                  {callsData ? `Showing ${callsData.calls.length} of ${callsData.total} calls` : 'No calls'}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setCallPage((page) => Math.max(1, page - 1))}
                    disabled={callPage === 1}
                    className="p-1 rounded border border-gray-300 disabled:opacity-50"
                  >
                    <ChevronLeft size={16} />
                  </button>
                  <span>Page {callPage}</span>
                  <button
                    onClick={() => setCallPage((page) => page + 1)}
                    disabled={callsData ? callPage * callLimit >= callsData.total : true}
                    className="p-1 rounded border border-gray-300 disabled:opacity-50"
                  >
                    <ChevronRight size={16} />
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>

      {callDetail && (
        <div className="fixed inset-0 bg-black bg-opacity-40 flex items-center justify-center z-50" onClick={closeCallDetail}>
          <div
            className="bg-white rounded-lg shadow-xl p-6 max-w-2xl w-full mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Call Detail</h3>
              <button onClick={closeCallDetail} className="text-gray-400 hover:text-gray-600">
                Close
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
              <div>
                <p className="text-gray-500">Call ID</p>
                <p className="font-medium text-gray-900">{callDetail.call_id}</p>
              </div>
              <div>
                <p className="text-gray-500">Queue</p>
                <p className="font-medium text-gray-900">{callDetail.queue || '—'}</p>
              </div>
              <div>
                <p className="text-gray-500">Agent</p>
                <p className="font-medium text-gray-900">{callDetail.agent || callDetail.agent_uuid || '—'}</p>
              </div>
              <div>
                <p className="text-gray-500">Caller</p>
                <p className="font-medium text-gray-900">{callDetail.caller_id_number || '—'}</p>
              </div>
              <div>
                <p className="text-gray-500">Start Time</p>
                <p className="font-medium text-gray-900">
                  {callDetail.start_time ? new Date(callDetail.start_time).toLocaleString() : '—'}
                </p>
              </div>
              <div>
                <p className="text-gray-500">End Time</p>
                <p className="font-medium text-gray-900">
                  {callDetail.end_time ? new Date(callDetail.end_time).toLocaleString() : '—'}
                </p>
              </div>
              <div>
                <p className="text-gray-500">Duration</p>
                <p className="font-medium text-gray-900">
                  {callDetail.duration === null || callDetail.duration === undefined
                    ? '—'
                    : formatSecondsToMmSs(callDetail.duration)}
                </p>
              </div>
              <div>
                <p className="text-gray-500">Billsec</p>
                <p className="font-medium text-gray-900">
                  {callDetail.billsec === null || callDetail.billsec === undefined
                    ? '—'
                    : formatSecondsToMmSs(callDetail.billsec)}
                </p>
              </div>
              <div>
                <p className="text-gray-500">MOS</p>
                <p className="font-medium text-gray-900">
                  {callDetail.rtp_audio_in_mos === null || callDetail.rtp_audio_in_mos === undefined
                    ? 'N/A'
                    : callDetail.rtp_audio_in_mos.toFixed(2)}
                </p>
              </div>
              <div>
                <p className="text-gray-500">Hangup Cause</p>
                <p className="font-medium text-gray-900">{callDetail.hangup_cause || '—'}</p>
              </div>
              <div>
                <p className="text-gray-500">CC Cancel Reason</p>
                <p className="font-medium text-gray-900">{callDetail.cc_cancel_reason || '—'}</p>
              </div>
              <div>
                <p className="text-gray-500">CC Cause</p>
                <p className="font-medium text-gray-900">{callDetail.cc_cause || '—'}</p>
              </div>
              <div>
                <p className="text-gray-500">Leg</p>
                <p className="font-medium text-gray-900">{callDetail.leg || '—'}</p>
              </div>
              <div>
                <p className="text-gray-500">Last App</p>
                <p className="font-medium text-gray-900">{callDetail.last_app || '—'}</p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
