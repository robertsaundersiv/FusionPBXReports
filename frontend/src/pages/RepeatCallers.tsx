import { useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, Search } from 'lucide-react';
import { useFilterStore } from '../hooks/useFilterStore';
import DashboardFilterBar from '../components/DashboardFilterBar';
import { dashboardService } from '../services/dashboard';
import type { Agent, DashboardFilters, Queue, RepeatCallersResponse, RepeatCallerRow } from '../types';

type SortField = 'call_count' | 'caller_id_number' | 'answered_count' | 'abandoned_count';
type SortOrder = 'asc' | 'desc';

interface TableState {
  sortField: SortField;
  sortOrder: SortOrder;
  searchQuery: string;
}

export default function RepeatCallers() {
  const { filters, updateDateRange, updateQueueIds, updateDirection } = useFilterStore();
  const [data, setData] = useState<RepeatCallersResponse | null>(null);
  const [queues, setQueues] = useState<Queue[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tableState, setTableState] = useState<TableState>({
    sortField: 'call_count',
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
    loadData();
  }, [filters]);

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await dashboardService.getRepeatCallers(filters);
      setData(response);
    } catch (err: any) {
      console.error('Error loading repeat callers:', err);
      setError(err.message || 'Failed to load repeat callers');
    } finally {
      setLoading(false);
    }
  };

  const handleFiltersChange = (newFilters: DashboardFilters) => {
    updateDateRange(newFilters.dateRange);
    updateQueueIds(newFilters.queueIds);
    updateDirection(newFilters.direction);
  };

  const displayRows = useMemo(() => {
    if (!data?.repeat_callers) return [];

    let rows: RepeatCallerRow[] = [...data.repeat_callers];

    if (tableState.searchQuery) {
      const query = tableState.searchQuery.toLowerCase();
      rows = rows.filter((row) =>
        row.caller_id_number.toLowerCase().includes(query) ||
        row.queues.some((queue) => queue.toLowerCase().includes(query))
      );
    }

    rows.sort((a, b) => {
      const aVal = a[tableState.sortField];
      const bVal = b[tableState.sortField];

      if (tableState.sortField === 'caller_id_number') {
        const comparison = String(aVal).localeCompare(String(bVal));
        return tableState.sortOrder === 'asc' ? comparison : -comparison;
      }

      const comparison = (aVal as number) - (bVal as number);
      return tableState.sortOrder === 'asc' ? comparison : -comparison;
    });

    return rows;
  }, [data, tableState]);

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

  const exportToCSV = () => {
    if (!data || displayRows.length === 0) return;

    const lines: string[] = [];
    lines.push(
      `Repeat Callers,Start: ${data.start},End: ${data.end},Generated: ${new Date().toISOString()}`
    );
    lines.push('');
    lines.push(
      ['Caller Number', 'Call Count', 'Answered', 'Abandoned', 'Queues'].map((header) =>
        `"${header}"`
      ).join(',')
    );

    displayRows.forEach((row) => {
      const queues = row.queues.length > 0 ? row.queues.join('; ') : 'Unassigned';
      lines.push(
        [
          row.caller_id_number,
          row.call_count,
          row.answered_count,
          row.abandoned_count,
          queues,
        ]
          .map((value) => `"${value}"`)
          .join(',')
      );
    });

    const csv = lines.join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `repeat-callers-${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(link);
    link.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(link);
  };

  if (loading) {
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
        />
        <div className="p-8 text-center">Loading Repeat Callers...</div>
      </div>
    );
  }

  if (error) {
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
        />
        <div className="p-8 text-center text-red-600">{error}</div>
      </div>
    );
  }

  if (!data || displayRows.length === 0) {
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
        />
        <div className="p-8 text-center text-gray-600">No repeat callers found for this window.</div>
      </div>
    );
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
      />

      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Repeat Callers</h1>
            <p className="text-sm text-gray-500 mt-1">
              Inbound callers with more than one call in the selected window
            </p>
          </div>
          <div className="flex items-center space-x-4">
            <p className="text-sm text-gray-600">{displayRows.length} repeat callers</p>
            <button
              onClick={exportToCSV}
              className="rounded-md border border-gray-200 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              Export CSV
            </button>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold">Repeat Caller Detail</h2>
            <div className="relative">
              <Search className="absolute left-3 top-2.5 text-gray-400" size={16} />
              <input
                type="text"
                placeholder="Search caller or queue"
                value={tableState.searchQuery}
                onChange={(event) =>
                  setTableState((prev) => ({ ...prev, searchQuery: event.target.value }))
                }
                className="pl-9 pr-3 py-2 border rounded-md text-sm"
              />
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="text-left border-b">
                  <th
                    className="py-2 px-3 cursor-pointer"
                    onClick={() => handleSort('caller_id_number')}
                  >
                    <SortIcon field="caller_id_number" label="Caller Number" />
                  </th>
                  <th
                    className="py-2 px-3 cursor-pointer"
                    onClick={() => handleSort('call_count')}
                  >
                    <SortIcon field="call_count" label="Call Count" />
                  </th>
                  <th
                    className="py-2 px-3 cursor-pointer"
                    onClick={() => handleSort('answered_count')}
                  >
                    <SortIcon field="answered_count" label="Answered" />
                  </th>
                  <th
                    className="py-2 px-3 cursor-pointer"
                    onClick={() => handleSort('abandoned_count')}
                  >
                    <SortIcon field="abandoned_count" label="Abandoned" />
                  </th>
                  <th className="py-2 px-3">Queues (A-Z)</th>
                </tr>
              </thead>
              <tbody>
                {displayRows.map((row) => (
                  <tr key={`${row.caller_id_number}-${row.call_count}`} className="border-b">
                    <td className="py-2 px-3 font-medium text-gray-900">{row.caller_id_number}</td>
                    <td className="py-2 px-3">{row.call_count}</td>
                    <td className="py-2 px-3">{row.answered_count}</td>
                    <td className="py-2 px-3">{row.abandoned_count}</td>
                    <td className="py-2 px-3 text-gray-700">
                      {row.queues.length > 0 ? row.queues.join(', ') : 'Unassigned'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
