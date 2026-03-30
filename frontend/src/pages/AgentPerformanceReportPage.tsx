import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ChevronDown, ChevronUp, Download, RefreshCw } from 'lucide-react';
import { useFilterStore } from '../hooks/useFilterStore';
import DashboardFilterBar from '../components/DashboardFilterBar';
import { dashboardService } from '../services/dashboard';
import { agentPerformanceService } from '../services/agentPerformance';
import type {
  Agent,
  AgentPerformanceReportResponse,
  AgentPerformanceReportRow,
  DashboardFilters,
  Queue,
} from '../types';

type SortField = 'agent_name' | 'handled_calls' | 'talk_time_sec' | 'aht_sec' | 'missed_calls';
type SortOrder = 'asc' | 'desc';

interface TableState {
  sortField: SortField;
  sortOrder: SortOrder;
  searchQuery: string;
}

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

export default function AgentPerformanceReportPage() {
  const {
    filters,
    updateDateRange,
    updateQueueIds,
    updateAgentUuids,
    updateTimezone,
    updateIncludeOutbound,
    updateExcludeDeflects,
  } = useFilterStore();

  const [data, setData] = useState<AgentPerformanceReportResponse | null>(null);
  const [queues, setQueues] = useState<Queue[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [outboundAddedCalls, setOutboundAddedCalls] = useState<number | null>(null);
  const requestRef = useRef(0);
  const [tableState, setTableState] = useState<TableState>({
    sortField: 'handled_calls',
    sortOrder: 'desc',
    searchQuery: '',
  });

  const canViewMissedCalls = Boolean(data?.can_view_missed_calls);

  useEffect(() => {
    const loadMetadata = async () => {
      try {
        const [queuesData, agentsData] = await Promise.all([
          dashboardService.getQueues(),
          dashboardService.getAgents(),
        ]);
        setQueues(queuesData);
        setAgents(agentsData);
      } catch (err) {
        console.error('Error loading metadata:', err);
      }
    };

    loadMetadata();
  }, []);

  useEffect(() => {
    // Avoid carrying agent selection from other pages (e.g., agent detail route)
    // so this report defaults to all visible agents.
    updateAgentUuids([]);
  }, [updateAgentUuids]);

  const loadData = useCallback(async () => {
    const requestId = ++requestRef.current;
    setLoading(true);
    setError(null);

    try {
      if (filters.includeOutbound) {
        const [reportResponse, leaderboardResponse] = await Promise.all([
          agentPerformanceService.getReport(filters),
          agentPerformanceService.getLeaderboard(filters),
        ]);
        if (requestId !== requestRef.current) {
          return;
        }
        setData(reportResponse);
        setOutboundAddedCalls(leaderboardResponse.outbound_added_calls ?? 0);
      } else {
        const response = await agentPerformanceService.getReport(filters);
        if (requestId !== requestRef.current) {
          return;
        }
        setData(response);
        setOutboundAddedCalls(null);
      }
    } catch (err: any) {
      if (requestId !== requestRef.current) {
        return;
      }
      console.error('Error loading agent performance report:', err);
      setError(err.message || 'Failed to load agent performance report');
      setOutboundAddedCalls(null);
    } finally {
      if (requestId === requestRef.current) {
        setLoading(false);
      }
    }
  }, [filters]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleFiltersChange = (newFilters: DashboardFilters) => {
    updateDateRange(newFilters.dateRange);
    updateQueueIds(newFilters.queueIds);
    updateAgentUuids(newFilters.agentUuids);
    updateTimezone(newFilters.timezone);
    updateIncludeOutbound(newFilters.includeOutbound);
    updateExcludeDeflects(newFilters.excludeDeflects);
  };

  const queueColumns = useMemo(() => {
    if (data?.queues && data.queues.length > 0) {
      return data.queues;
    }
    if (filters.queueIds.length > 0) {
      return queues
        .filter((queue) => filters.queueIds.includes(String(queue.queue_id)))
        .map((queue) => ({ queue_id: String(queue.queue_id), queue_name: queue.name }));
    }
    return queues.map((queue) => ({ queue_id: String(queue.queue_id), queue_name: queue.name }));
  }, [data?.queues, filters.queueIds, queues]);

  const displayAgents = useMemo(() => {
    if (!data?.agents) {
      return [];
    }

    let filtered = [...data.agents];

    if (tableState.searchQuery) {
      const query = tableState.searchQuery.toLowerCase();
      filtered = filtered.filter((agent) => agent.agent_name.toLowerCase().includes(query));
    }

    filtered.sort((a, b) => {
      const aVal = a[tableState.sortField];
      const bVal = b[tableState.sortField];

      if (tableState.sortField === 'agent_name') {
        const comparison = String(aVal).localeCompare(String(bVal));
        return tableState.sortOrder === 'asc' ? comparison : -comparison;
      }

      const aNum = typeof aVal === 'number' ? aVal : 0;
      const bNum = typeof bVal === 'number' ? bVal : 0;
      const comparison = aNum - bNum;
      return tableState.sortOrder === 'asc' ? comparison : -comparison;
    });

    return filtered;
  }, [data?.agents, tableState]);

  const handleSort = (field: SortField) => {
    setTableState((prev) => {
      if (prev.sortField === field) {
        return {
          ...prev,
          sortOrder: prev.sortOrder === 'asc' ? 'desc' : 'asc',
        };
      }
      return {
        ...prev,
        sortField: field,
        sortOrder: 'desc',
      };
    });
  };

  const SortIcon = ({ field, label }: { field: SortField; label: string }) => {
    if (tableState.sortField !== field) {
      return <span className="text-gray-400">{label}</span>;
    }
    return (
      <span className="flex items-center space-x-1">
        <span>{label}</span>
        {tableState.sortOrder === 'asc' ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
      </span>
    );
  };

  const getQueueMetrics = (agent: AgentPerformanceReportRow, queueId: string) => {
    return agent.queues?.[queueId] || { handled_calls: 0, talk_time_sec: 0, missed_calls: 0 };
  };

  const exportToCSV = () => {
    if (!data?.agents || data.agents.length === 0) return;

    const lines: string[] = [];
    lines.push(
      `Agent Performance Report,Start: ${data.start},End: ${data.end},Generated: ${new Date().toISOString()}`
    );
    lines.push('');

    const headers = [
      'Agent Name',
      'Calls Handled',
      'Talk Time Total (sec)',
      'Average Handle Time (sec)',
    ];

    if (canViewMissedCalls) {
      headers.push('Missed Calls');
    }

    queueColumns.forEach((queue) => {
      headers.push(`${queue.queue_name} Calls Handled`);
      headers.push(`${queue.queue_name} Talk Time (sec)`);
      if (canViewMissedCalls) {
        headers.push(`${queue.queue_name} Missed Calls`);
      }
    });

    lines.push(headers.map((header) => `"${header}"`).join(','));

    displayAgents.forEach((agent) => {
      const baseRow: Array<string | number> = [
        `"${agent.agent_name}"`,
        agent.handled_calls,
        agent.talk_time_sec,
        agent.aht_sec ?? '',
      ];

      if (canViewMissedCalls) {
        baseRow.push(agent.missed_calls);
      }

      const queueValues = queueColumns.flatMap((queue) => {
        const metrics = getQueueMetrics(agent, queue.queue_id);
        if (canViewMissedCalls) {
          return [metrics.handled_calls, metrics.talk_time_sec, metrics.missed_calls];
        }
        return [metrics.handled_calls, metrics.talk_time_sec];
      });

      lines.push([...baseRow, ...queueValues].join(','));
    });

    const csv = lines.join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `agent-performance-report-${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(link);
    link.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(link);
  };

  if (error && !data) {
    return (
      <div className="p-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <h3 className="font-semibold text-red-900">Error Loading Report</h3>
          <p className="text-sm text-red-700">{error}</p>
          <button
            onClick={loadData}
            className="mt-3 flex items-center space-x-2 rounded bg-red-600 px-4 py-2 text-white hover:bg-red-700"
          >
            <RefreshCw size={16} />
            <span>Retry</span>
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col space-y-6 p-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Agent Performance Report</h1>
          <p className="mt-1 text-gray-600">Per-agent totals with queue-level breakdowns</p>
        </div>
        <button
          onClick={loadData}
          className="flex items-center space-x-2 rounded-lg bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
          disabled={loading}
        >
          <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
          <span>Refresh</span>
        </button>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <DashboardFilterBar
          filters={filters}
          queues={queues}
          agents={agents.filter(
            (agent): agent is { agent_uuid?: string; agent_id?: string | number; agent_name: string } =>
              Boolean(agent.agent_uuid) || agent.agent_id !== undefined
          )}
          onFiltersChange={handleFiltersChange}
          showAgents={true}
          showDirection={false}
          showOutboundToggle={true}
          showExcludeDeflectsToggle={false}
          outboundBadgeText={
            outboundAddedCalls !== null
              ? `+${outboundAddedCalls.toLocaleString()} attributed calls`
              : undefined
          }
        />
      </div>

      <div className="flex justify-end">
        <button
          onClick={exportToCSV}
          className="flex items-center space-x-2 rounded-lg bg-green-600 px-4 py-2 text-white hover:bg-green-700"
          disabled={!data?.agents || data.agents.length === 0}
        >
          <Download size={18} />
          <span>Export CSV</span>
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          <thead className="sticky top-0 bg-gray-50">
            <tr className="border-b border-gray-200">
              <th rowSpan={2} className="bg-gray-50 px-4 py-3 text-left">
                <button
                  onClick={() => handleSort('agent_name')}
                  className="flex items-center space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  <SortIcon field="agent_name" label="Agent" />
                </button>
              </th>
              <th rowSpan={2} className="bg-gray-50 px-4 py-3 text-right">
                <button
                  onClick={() => handleSort('handled_calls')}
                  className="flex items-center justify-end space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  <SortIcon field="handled_calls" label="Calls Handled" />
                </button>
              </th>
              <th rowSpan={2} className="bg-gray-50 px-4 py-3 text-right">
                <button
                  onClick={() => handleSort('talk_time_sec')}
                  className="flex items-center justify-end space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  <SortIcon field="talk_time_sec" label="Talk Time" />
                </button>
              </th>
              <th rowSpan={2} className="bg-gray-50 px-4 py-3 text-right">
                <button
                  onClick={() => handleSort('aht_sec')}
                  className="flex items-center justify-end space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  <SortIcon field="aht_sec" label="Avg Handle" />
                </button>
              </th>
              {canViewMissedCalls ? (
                <th rowSpan={2} className="bg-gray-50 px-4 py-3 text-right">
                  <button
                    onClick={() => handleSort('missed_calls')}
                    className="flex items-center justify-end space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                  >
                    <SortIcon field="missed_calls" label="Missed" />
                  </button>
                </th>
              ) : null}
              {queueColumns.map((queue) => (
                <th
                  key={queue.queue_id}
                  colSpan={canViewMissedCalls ? 3 : 2}
                  className="border-l border-gray-200 bg-gray-50 px-4 py-3 text-center font-semibold text-gray-900"
                >
                  {queue.queue_name}
                </th>
              ))}
            </tr>
            <tr className="border-b border-gray-200">
              {queueColumns.map((queue) => (
                <Fragment key={`${queue.queue_id}-subheaders`}>
                  <th
                    className="border-l border-gray-200 bg-gray-50 px-4 py-2 text-right text-sm font-semibold text-gray-700"
                  >
                    Handled
                  </th>
                  <th
                    className="bg-gray-50 px-4 py-2 text-right text-sm font-semibold text-gray-700"
                  >
                    Talk Time
                  </th>
                  {canViewMissedCalls ? (
                    <th
                      className="bg-gray-50 px-4 py-2 text-right text-sm font-semibold text-gray-700"
                    >
                      Missed
                    </th>
                  ) : null}
                </Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayAgents.length === 0 && !loading ? (
              <tr>
                <td colSpan={(canViewMissedCalls ? 5 : 4) + queueColumns.length * (canViewMissedCalls ? 3 : 2)} className="px-6 py-6 text-center text-gray-500">
                  No agents found for the selected filters.
                </td>
              </tr>
            ) : (
              displayAgents.map((agent) => (
                <tr key={agent.agent_id} className="border-b border-gray-100">
                  <td className="px-4 py-3 text-left text-gray-900">{agent.agent_name}</td>
                  <td className="px-4 py-3 text-right text-gray-900">{agent.handled_calls}</td>
                  <td className="px-4 py-3 text-right text-gray-900">
                    {formatSecondsToHms(agent.talk_time_sec)}
                  </td>
                  <td className="px-4 py-3 text-right text-gray-900">
                    {formatSecondsToMmSs(agent.aht_sec)}
                  </td>
                  {canViewMissedCalls ? <td className="px-4 py-3 text-right text-gray-900">{agent.missed_calls}</td> : null}
                  {queueColumns.map((queue) => {
                    const metrics = getQueueMetrics(agent, queue.queue_id);
                    return (
                      <Fragment key={`${agent.agent_id}-${queue.queue_id}`}>
                        <td className="border-l border-gray-100 px-4 py-3 text-right text-gray-900">
                          {metrics.handled_calls}
                        </td>
                        <td className="px-4 py-3 text-right text-gray-900">
                          {formatSecondsToHms(metrics.talk_time_sec)}
                        </td>
                        {canViewMissedCalls ? (
                          <td className="px-4 py-3 text-right text-gray-900">
                            {metrics.missed_calls}
                          </td>
                        ) : null}
                      </Fragment>
                    );
                  })}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
