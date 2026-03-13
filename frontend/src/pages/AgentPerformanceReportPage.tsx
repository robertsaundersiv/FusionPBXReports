import { Fragment, useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, Download, RefreshCw, Search } from 'lucide-react';
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
    updateIncludeOutbound,
    updateExcludeDeflects,
  } = useFilterStore();

  const [data, setData] = useState<AgentPerformanceReportResponse | null>(null);
  const [queues, setQueues] = useState<Queue[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tableState, setTableState] = useState<TableState>({
    sortField: 'handled_calls',
    sortOrder: 'desc',
    searchQuery: '',
  });

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

  useEffect(() => {
    loadData();
  }, [filters]);

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await agentPerformanceService.getReport(filters);
      setData(response);
    } catch (err: any) {
      console.error('Error loading agent performance report:', err);
      setError(err.message || 'Failed to load agent performance report');
    } finally {
      setLoading(false);
    }
  };

  const handleFiltersChange = (newFilters: DashboardFilters) => {
    updateDateRange(newFilters.dateRange);
    updateQueueIds(newFilters.queueIds);
    updateAgentUuids(newFilters.agentUuids);
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
      'Missed Calls',
    ];

    queueColumns.forEach((queue) => {
      headers.push(`${queue.queue_name} Calls Handled`);
      headers.push(`${queue.queue_name} Talk Time (sec)`);
      headers.push(`${queue.queue_name} Missed Calls`);
    });

    lines.push(headers.map((header) => `"${header}"`).join(','));

    displayAgents.forEach((agent) => {
      const baseRow = [
        `"${agent.agent_name}"`,
        agent.handled_calls,
        agent.talk_time_sec,
        agent.aht_sec ?? '',
        agent.missed_calls,
      ];

      const queueValues = queueColumns.flatMap((queue) => {
        const metrics = getQueueMetrics(agent, queue.queue_id);
        return [metrics.handled_calls, metrics.talk_time_sec, metrics.missed_calls];
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
          showExcludeDeflectsToggle={true}
        />
      </div>

      <div className="flex items-center justify-between">
        <div className="flex-1">
          <div className="relative">
            <Search size={18} className="absolute left-3 top-3 text-gray-400" />
            <input
              type="text"
              placeholder="Search agent names..."
              value={tableState.searchQuery}
              onChange={(e) =>
                setTableState((prev) => ({
                  ...prev,
                  searchQuery: e.target.value,
                }))
              }
              className="w-full rounded-lg border border-gray-300 bg-white py-2 pl-10 pr-4 text-gray-900 placeholder-gray-500 focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
            />
          </div>
        </div>
        <button
          onClick={exportToCSV}
          className="ml-4 flex items-center space-x-2 rounded-lg bg-green-600 px-4 py-2 text-white hover:bg-green-700"
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
              <th rowSpan={2} className="bg-gray-50 px-4 py-3 text-right">
                <button
                  onClick={() => handleSort('missed_calls')}
                  className="flex items-center justify-end space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  <SortIcon field="missed_calls" label="Missed" />
                </button>
              </th>
              {queueColumns.map((queue) => (
                <th
                  key={queue.queue_id}
                  colSpan={3}
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
                  <th
                    className="bg-gray-50 px-4 py-2 text-right text-sm font-semibold text-gray-700"
                  >
                    Missed
                  </th>
                </Fragment>
              ))}
            </tr>
          </thead>
          <tbody>
            {displayAgents.length === 0 && !loading ? (
              <tr>
                <td colSpan={5 + queueColumns.length * 3} className="px-6 py-6 text-center text-gray-500">
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
                  <td className="px-4 py-3 text-right text-gray-900">{agent.missed_calls}</td>
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
                        <td className="px-4 py-3 text-right text-gray-900">
                          {metrics.missed_calls}
                        </td>
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
