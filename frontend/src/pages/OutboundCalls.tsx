import { useCallback, useEffect, useMemo, useState } from 'react';
import { ChevronDown, ChevronUp, Search } from 'lucide-react';
import { useFilterStore } from '../hooks/useFilterStore';
import DashboardFilterBar from '../components/DashboardFilterBar';
import { dashboardService } from '../services/dashboard';
import type { DashboardFilters, OutboundCallsResponse, OutboundCallUserRow, OutboundCallPrefixRow } from '../types';

type SortField = 'agent_name' | 'count' | 'aht_seconds' | 'prefix';
type SortOrder = 'asc' | 'desc';

interface TableState {
  sortField: SortField;
  sortOrder: SortOrder;
  searchQuery: string;
}

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

export default function OutboundCalls() {
  const { filters, updateDateRange, updateQueueIds, updateAgentUuids, updateTimezone } = useFilterStore();
  const [data, setData] = useState<OutboundCallsResponse | null>(null);
  const [queues, setQueues] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tableState, setTableState] = useState<TableState>({
    sortField: 'count',
    sortOrder: 'desc',
    searchQuery: '',
  });
  const diagnostics = data?.diagnostics;

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
    // Avoid carrying agent selection from other pages; outbound report is queue/date scoped.
    updateAgentUuids([]);
  }, [updateAgentUuids]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await dashboardService.getOutboundCalls(filters);
      setData(response);
    } catch (err: any) {
      console.error('Error loading outbound calls:', err);
      setError(err.message || 'Failed to load outbound calls');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleFiltersChange = (newFilters: DashboardFilters) => {
    updateDateRange(newFilters.dateRange);
    updateQueueIds(newFilters.queueIds);
    updateTimezone(newFilters.timezone);
  };

  // Display rows for "By User" table
  const displayByUserRows = useMemo(() => {
    if (!data?.by_user) return [];

    let rows: OutboundCallUserRow[] = [...data.by_user];

    if (tableState.searchQuery) {
      const query = tableState.searchQuery.toLowerCase();
      rows = rows.filter((row) =>
        row.agent_name.toLowerCase().includes(query)
      );
    }

    rows.sort((a, b) => {
      // User table only supports agent_name, count, aht_seconds
      let field = tableState.sortField as keyof OutboundCallUserRow;
      if (!['agent_name', 'count', 'aht_seconds'].includes(field)) {
        field = 'count';
      }

      const aVal = a[field];
      const bVal = b[field];

      if (field === 'agent_name') {
        const comparison = String(aVal).localeCompare(String(bVal));
        return tableState.sortOrder === 'asc' ? comparison : -comparison;
      }

      const comparison = (aVal as number) - (bVal as number);
      return tableState.sortOrder === 'asc' ? comparison : -comparison;
    });

    return rows;
  }, [data, tableState]);

  // Display rows for "By Prefix" table
  const displayByPrefixRows = useMemo(() => {
    if (!data?.by_prefix) return [];

    let rows: OutboundCallPrefixRow[] = [...data.by_prefix];

    // For prefix table, only search if sortField is 'prefix'
    if (tableState.searchQuery && tableState.sortField === 'prefix') {
      const query = tableState.searchQuery.toLowerCase();
      rows = rows.filter((row) =>
        row.prefix.toLowerCase().includes(query)
      );
    }

    rows.sort((a, b) => {
      // Prefix table sorting
      let field = tableState.sortField as keyof OutboundCallPrefixRow;
      if (!['prefix', 'count', 'aht_seconds'].includes(field)) {
        field = 'count';
      }

      const aVal = a[field];
      const bVal = b[field];

      if (field === 'prefix') {
        const comparison = String(aVal).localeCompare(String(bVal));
        return tableState.sortOrder === 'asc' ? comparison : -comparison;
      }

      const comparison = (aVal as number) - (bVal as number);
      return tableState.sortOrder === 'asc' ? comparison : -comparison;
    });

    return rows;
  }, [data, tableState]);

  const toggleSort = (field: SortField) => {
    if (tableState.sortField === field) {
      setTableState({
        ...tableState,
        sortOrder: tableState.sortOrder === 'asc' ? 'desc' : 'asc',
      });
    } else {
      setTableState({
        ...tableState,
        sortField: field,
        sortOrder: 'desc',
      });
    }
  };

  const exportOutboundCallsCsv = () => {
    if (!data) {
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
      `Outbound Calls Report,Start: ${startLabel},End: ${endLabel},Generated: ${new Date().toISOString()}`
    );
    lines.push('');

    lines.push('Outbound Calls by Agent');
    lines.push(['Agent', 'Count', 'AHT (mm:ss)'].map((column) => `"${column}"`).join(','));
    if (displayByUserRows.length === 0) {
      lines.push('No data');
    } else {
      displayByUserRows.forEach((row) => {
        lines.push(
          [
            row.agent_name,
            row.count,
            formatSecondsToMmSs(row.aht_seconds),
          ].map(formatCsvValue).join(',')
        );
      });
    }

    lines.push('');
    lines.push('Outbound Calls by Prefix (First 3 Letters)');
    lines.push(['Prefix', 'Count', 'AHT (mm:ss)'].map((column) => `"${column}"`).join(','));
    if (displayByPrefixRows.length === 0) {
      lines.push('No data');
    } else {
      displayByPrefixRows.forEach((row) => {
        lines.push(
          [
            row.prefix,
            row.count,
            formatSecondsToMmSs(row.aht_seconds),
          ].map(formatCsvValue).join(',')
        );
      });
    }

    const csv = lines.join('\n');
    const startFileLabel = filters.dateRange.startDate
      ? filters.dateRange.startDate.toISOString().slice(0, 10)
      : 'start';
    const endFileLabel = filters.dateRange.endDate
      ? filters.dateRange.endDate.toISOString().slice(0, 10)
      : 'end';
    const filename = `outbound_calls_${startFileLabel}_to_${endFileLabel}.csv`;

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

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-6 space-y-6">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-2">Outbound Calls</h1>
            <p className="text-gray-600">Analysis of outbound call activity by agent and prefix group</p>
          </div>
          <button
            type="button"
            onClick={exportOutboundCallsCsv}
            className="text-sm px-3 py-1.5 border border-gray-300 rounded-md text-gray-700 hover:bg-gray-50"
            disabled={!data || (!displayByUserRows.length && !displayByPrefixRows.length)}
          >
            Export CSV
          </button>
        </div>

        <DashboardFilterBar 
          filters={filters} 
          queues={queues} 
          agents={agents} 
          onFiltersChange={handleFiltersChange}
          showQueues={false}
          showDirection={false}
        />

        {diagnostics && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
            <h2 className="text-base font-semibold text-amber-900">Outbound Attribution Diagnostics</h2>
            <p className="mt-1 text-sm text-amber-800">
              Unknown records: <span className="font-semibold">{diagnostics.unknown_records.toLocaleString()}</span> / {diagnostics.total_records.toLocaleString()} ({diagnostics.unknown_rate_pct}%)
            </p>
          </div>
        )}

        {error && (
          <div className="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded">
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex justify-center items-center h-64">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
          </div>
        ) : (
          <div className="space-y-8">
            {/* By User Table */}
            <div className="bg-white rounded-lg shadow">
              <div className="px-6 py-4 border-b border-gray-200">
                <div className="flex justify-between items-center">
                  <h2 className="text-xl font-semibold text-gray-900">Outbound Calls by Agent</h2>
                  <div className="flex items-center bg-gray-50 border border-gray-300 rounded-lg px-3 py-2 w-64">
                    <Search size={18} className="text-gray-400" />
                    <input
                      type="text"
                      placeholder="Search agents..."
                      value={tableState.searchQuery}
                      onChange={(e) => setTableState({ ...tableState, searchQuery: e.target.value })}
                      className="bg-transparent ml-2 w-full outline-none text-sm"
                    />
                  </div>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr>
                      <th className="px-6 py-3 text-left">
                        <button
                          onClick={() => toggleSort('agent_name')}
                          className="flex items-center font-semibold text-gray-700 hover:text-gray-900"
                        >
                          Agent Name
                          {tableState.sortField === 'agent_name' && (
                            tableState.sortOrder === 'asc' ? <ChevronUp size={16} className="ml-1" /> : <ChevronDown size={16} className="ml-1" />
                          )}
                        </button>
                      </th>
                      <th className="px-6 py-3 text-right">
                        <button
                          onClick={() => toggleSort('count')}
                          className="flex items-center justify-end font-semibold text-gray-700 hover:text-gray-900 w-full"
                        >
                          Count
                          {tableState.sortField === 'count' && (
                            tableState.sortOrder === 'asc' ? <ChevronUp size={16} className="ml-1" /> : <ChevronDown size={16} className="ml-1" />
                          )}
                        </button>
                      </th>
                      <th className="px-6 py-3 text-right">
                        <button
                          onClick={() => toggleSort('aht_seconds')}
                          className="flex items-center justify-end font-semibold text-gray-700 hover:text-gray-900 w-full"
                        >
                          AHT
                          {tableState.sortField === 'aht_seconds' && (
                            tableState.sortOrder === 'asc' ? <ChevronUp size={16} className="ml-1" /> : <ChevronDown size={16} className="ml-1" />
                          )}
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayByUserRows.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="px-6 py-4 text-center text-gray-500">
                          No data available
                        </td>
                      </tr>
                    ) : (
                      displayByUserRows.map((row, idx) => (
                        <tr key={row.agent_name} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                          <td className="px-6 py-3 text-gray-900">{row.agent_name}</td>
                          <td className="px-6 py-3 text-right text-gray-900 font-medium">{row.count}</td>
                          <td className="px-6 py-3 text-right text-gray-900">{formatSecondsToMmSs(row.aht_seconds)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* By Prefix Table */}
            <div className="bg-white rounded-lg shadow">
              <div className="px-6 py-4 border-b border-gray-200">
                <div className="flex justify-between items-center">
                  <h2 className="text-xl font-semibold text-gray-900">Outbound Calls by Prefix (First 3 Letters)</h2>
                  <div className="flex items-center bg-gray-50 border border-gray-300 rounded-lg px-3 py-2 w-64">
                    <Search size={18} className="text-gray-400" />
                    <input
                      type="text"
                      placeholder="Search prefix..."
                      value={tableState.sortField === 'prefix' ? tableState.searchQuery : ''}
                      onChange={(e) => {
                        if (tableState.sortField === 'prefix') {
                          setTableState({ ...tableState, searchQuery: e.target.value });
                        }
                      }}
                      className="bg-transparent ml-2 w-full outline-none text-sm"
                    />
                  </div>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr>
                      <th className="px-6 py-3 text-left">
                        <button
                          onClick={() => toggleSort('prefix')}
                          className="flex items-center font-semibold text-gray-700 hover:text-gray-900"
                        >
                          Prefix
                          {tableState.sortField === 'prefix' && (
                            tableState.sortOrder === 'asc' ? <ChevronUp size={16} className="ml-1" /> : <ChevronDown size={16} className="ml-1" />
                          )}
                        </button>
                      </th>
                      <th className="px-6 py-3 text-right">
                        <button
                          onClick={() => toggleSort('count')}
                          className="flex items-center justify-end font-semibold text-gray-700 hover:text-gray-900 w-full"
                        >
                          Count
                          {tableState.sortField === 'count' && (
                            tableState.sortOrder === 'asc' ? <ChevronUp size={16} className="ml-1" /> : <ChevronDown size={16} className="ml-1" />
                          )}
                        </button>
                      </th>
                      <th className="px-6 py-3 text-right">
                        <button
                          onClick={() => toggleSort('aht_seconds')}
                          className="flex items-center justify-end font-semibold text-gray-700 hover:text-gray-900 w-full"
                        >
                          AHT
                          {tableState.sortField === 'aht_seconds' && (
                            tableState.sortOrder === 'asc' ? <ChevronUp size={16} className="ml-1" /> : <ChevronDown size={16} className="ml-1" />
                          )}
                        </button>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayByPrefixRows.length === 0 ? (
                      <tr>
                        <td colSpan={3} className="px-6 py-4 text-center text-gray-500">
                          No data available
                        </td>
                      </tr>
                    ) : (
                      displayByPrefixRows.map((row, idx) => (
                        <tr key={row.prefix} className={idx % 2 === 0 ? 'bg-white' : 'bg-gray-50'}>
                          <td className="px-6 py-3 text-gray-900 font-mono font-medium">{row.prefix}</td>
                          <td className="px-6 py-3 text-right text-gray-900 font-medium">{row.count}</td>
                          <td className="px-6 py-3 text-right text-gray-900">{formatSecondsToMmSs(row.aht_seconds)}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
