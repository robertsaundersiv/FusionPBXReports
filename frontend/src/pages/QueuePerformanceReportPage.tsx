import { useState, useEffect, useMemo, useCallback } from 'react';
import {
  ChevronUp,
  ChevronDown,
  Download,
  Search,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import { useFilterStore } from '../hooks/useFilterStore';
import DashboardFilterBar from '../components/DashboardFilterBar';
import { dashboardService } from '../services/dashboard';
import type { QueuePerformanceReportResponse, DashboardFilters, Queue, Agent } from '../types';

type SortField =
  | 'queue_name'
  | 'offered'
  | 'answered'
  | 'abandoned'
  | 'answer_rate'
  | 'service_level_30'
  | 'asa_sec'
  | 'aht_sec';
type SortOrder = 'asc' | 'desc';

interface TableState {
  sortField: SortField;
  sortOrder: SortOrder;
  searchQuery: string;
}

interface ReportRow {
  queue_id: string;
  queue_name: string;
  offered: number;
  answered: number;
  abandoned: number;
  answer_rate: number;
  service_level_30: number;
  asa_sec: number;
  aht_sec: number;
  sl30_numerator: number;
  sl30_denominator: number;
  asa_answered_count: number;
  aht_answered_count: number;
}

export default function QueuePerformanceReportPage() {
  const {
    filters,
    updateDateRange,
    updateQueueIds,
    updateDirection,
    updateTimezone,
    updateExcludeDeflects,
  } = useFilterStore();
  const [data, setData] = useState<QueuePerformanceReportResponse | null>(null);
  const [queues, setQueues] = useState<Queue[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tableState, setTableState] = useState<TableState>({
    sortField: 'offered',
    sortOrder: 'desc',
    searchQuery: '',
  });

  // Load metadata on mount
  useEffect(() => {
    const loadMetadata = async () => {
      try {
        const [queuesData, agentsData] = await Promise.all([
          dashboardService.getQueues(),
          dashboardService.getAgents(),
        ]);
        console.log('Loaded queues:', queuesData);
        console.log('Loaded agents:', agentsData);
        setQueues(queuesData);
        setAgents(agentsData);
      } catch (err) {
        console.error('Error loading metadata:', err);
      }
    };
    loadMetadata();
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      console.log('📊 Loading Queue Performance Report with filters:', filters);
      const response = await dashboardService.getQueuePerformanceReport(filters);
      console.log('📈 Queue Performance Report Response:', response);
      setData(response);
      setLoading(false);
    } catch (err: any) {
      console.error('Error loading queue performance report:', err);
      setError(err.message || 'Failed to load queue performance report');
      setLoading(false);
    }
  }, [filters]);

  // Load data when filters change
  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleRetry = () => {
    loadData();
  };

  const handleFiltersChange = (newFilters: DashboardFilters) => {
    updateDateRange(newFilters.dateRange);
    updateQueueIds(newFilters.queueIds);
    updateDirection(newFilters.direction);
    updateTimezone(newFilters.timezone);
    updateExcludeDeflects(newFilters.excludeDeflects);
  };

  // Filter and sort data
  const displayData = useMemo(() => {
    if (!data?.rows) return [];

    let filtered: ReportRow[] = data.rows.map((row) => ({
      ...row,
      answer_rate: row.offered > 0 ? (row.answered / row.offered) * 100 : 0,
    }));

    // Apply search filter
    if (tableState.searchQuery) {
      const query = tableState.searchQuery.toLowerCase();
      filtered = filtered.filter((row) =>
        row.queue_name.toLowerCase().includes(query)
      );
    }

    // Apply sorting
    filtered.sort((a, b) => {
      const aVal = a[tableState.sortField];
      const bVal = b[tableState.sortField];

      if (aVal === undefined || aVal === null) return 1;
      if (bVal === undefined || bVal === null) return -1;

      let comparison = 0;
      if (typeof aVal === 'string') {
        comparison = aVal.localeCompare(bVal as string);
      } else {
        comparison = (aVal as number) - (bVal as number);
      }

      return tableState.sortOrder === 'asc' ? comparison : -comparison;
    });

    return filtered;
  }, [data, tableState]);

  // Calculate totals
  const totals = useMemo(() => {
    if (!displayData || displayData.length === 0) {
      return {
        offered: 0,
        answered: 0,
        abandoned: 0,
        service_level_30: 0,
        asa_sec: 0,
        aht_sec: 0,
      };
    }

    const totalOffered = displayData.reduce((sum, row) => sum + row.offered, 0);
    const totalAnswered = displayData.reduce((sum, row) => sum + row.answered, 0);
    const totalAbandoned = displayData.reduce((sum, row) => sum + row.abandoned, 0);

    // Weighted Service Level: total_within_30 / total_offered_answered
    const totalSL30Num = displayData.reduce((sum, row) => sum + row.sl30_numerator, 0);
    const totalSL30Denom = displayData.reduce((sum, row) => sum + row.sl30_denominator, 0);
    const serviceLevelTotal = totalSL30Denom > 0 ? (totalSL30Num / totalSL30Denom) * 100 : 0;

    // Weighted ASA: sum_wait_time / total_answered
    const totalAsaCount = displayData.reduce((sum, row) => sum + row.asa_answered_count, 0);
    const totalAsaSum = displayData.reduce((sum, row) => sum + row.asa_sec * row.asa_answered_count, 0);
    const asaTotal = totalAsaCount > 0 ? totalAsaSum / totalAsaCount : 0;

    // Weighted AHT: sum_talk_time / total_answered
    const totalAhtCount = displayData.reduce((sum, row) => sum + row.aht_answered_count, 0);
    const totalAhtSum = displayData.reduce((sum, row) => sum + row.aht_sec * row.aht_answered_count, 0);
    const ahtTotal = totalAhtCount > 0 ? totalAhtSum / totalAhtCount : 0;

    return {
      offered: totalOffered,
      answered: totalAnswered,
      abandoned: totalAbandoned,
      service_level_30: Math.round(serviceLevelTotal * 100) / 100,
      asa_sec: Math.round(asaTotal * 100) / 100,
      aht_sec: Math.round(ahtTotal * 100) / 100,
    };
  }, [displayData]);

  const handleSort = (field: SortField) => {
    setTableState((prev) => {
      if (prev.sortField === field) {
        // Toggle sort order
        return {
          ...prev,
          sortOrder: prev.sortOrder === 'asc' ? 'desc' : 'asc',
        };
      } else {
        // New field, default to descending
        return {
          ...prev,
          sortField: field,
          sortOrder: 'desc',
        };
      }
    });
  };

  const renderSortLabel = (field: SortField, label: string) => {
    if (tableState.sortField !== field) {
      return <span className="text-gray-400">{label}</span>;
    }
    return (
      <span className="flex items-center space-x-1">
        <span>{label}</span>
        {tableState.sortOrder === 'asc' ? (
          <ChevronUp size={16} />
        ) : (
          <ChevronDown size={16} />
        )}
      </span>
    );
  };

  const exportToCSV = () => {
    if (!data?.rows || data.rows.length === 0) return;

    // Header with metadata
    const lines: string[] = [];
    lines.push(
      `Queue Performance Report,Start: ${data.start},End: ${data.end},Generated: ${new Date().toISOString()}`
    );
    lines.push(''); // Blank line

    // Column headers
    const headers = [
      'Queue Name',
      'Offered',
      'Answered',
      'Abandoned',
      'Answer Rate (%)',
      'Service Level 30 (%)',
      'ASA (sec)',
      'AHT (sec)',
    ];
    lines.push(headers.map((h) => `"${h}"`).join(','));

    // Data rows
    displayData.forEach((row) => {
      const answerRate = row.offered > 0 ? ((row.answered / row.offered) * 100).toFixed(2) : '0';
      lines.push(
        [
          `"${row.queue_name}"`,
          row.offered,
          row.answered,
          row.abandoned,
          answerRate,
          row.service_level_30.toFixed(2),
          row.asa_sec.toFixed(2),
          row.aht_sec.toFixed(2),
        ].join(',')
      );
    });

    // Totals row
    const totalAnswerRate = totals.offered > 0 ? ((totals.answered / totals.offered) * 100).toFixed(2) : '0';
    lines.push(''); // Blank line
    lines.push(['TOTAL', totals.offered, totals.answered, totals.abandoned, totalAnswerRate, totals.service_level_30.toFixed(2), totals.asa_sec.toFixed(2), totals.aht_sec.toFixed(2)].join(','));

    // Create blob and download
    const csv = lines.join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `queue-performance-report-${new Date().toISOString().split('T')[0]}.csv`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);
  };

  if (error && !data) {
    return (
      <div className="p-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-4">
          <div className="flex items-center">
            <AlertCircle className="text-red-600" size={24} />
            <div className="ml-4">
              <h3 className="font-semibold text-red-900">Error Loading Report</h3>
              <p className="text-sm text-red-700">{error}</p>
              <button
                onClick={handleRetry}
                className="mt-2 flex items-center space-x-2 rounded bg-red-600 px-4 py-2 text-white hover:bg-red-700"
              >
                <RefreshCw size={16} />
                <span>Retry</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col space-y-6 p-8">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Queue Performance Report</h1>
          <p className="mt-1 text-gray-600">
            Exportable table of queue KPIs aligned with dashboard metrics
          </p>
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

      {/* Filter Bar */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <DashboardFilterBar
          filters={filters}
          queues={queues}
          agents={agents.filter((agent) => agent.agent_id !== undefined) as { agent_id: string | number; agent_name: string; }[]}
          onFiltersChange={handleFiltersChange}
          showAgents={false}
          showDirection={false}
          showOutboundToggle={false}
          showExcludeDeflectsToggle={false}
        />
      </div>

      {/* Controls Bar */}
      <div className="flex items-center justify-between">
        <div className="flex-1">
          <div className="relative">
            <Search
              size={18}
              className="absolute left-3 top-3 text-gray-400"
            />
            <input
              type="text"
              placeholder="Search queue names..."
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
          disabled={!data?.rows || data.rows.length === 0}
        >
          <Download size={18} />
          <span>Export CSV</span>
        </button>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-200">
        <table className="w-full">
          {/* Header */}
          <thead className="sticky top-0 bg-gray-50">
            <tr className="border-b border-gray-200">
              <th className="bg-gray-50 px-6 py-3 text-left">
                <button
                  onClick={() => handleSort('queue_name')}
                  className="flex items-center space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  {renderSortLabel('queue_name', 'Queue Name')}
                </button>
              </th>
              <th className="bg-gray-50 px-6 py-3 text-right">
                <button
                  onClick={() => handleSort('offered')}
                  className="flex items-center justify-end space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  {renderSortLabel('offered', 'Offered')}
                </button>
              </th>
              <th className="bg-gray-50 px-6 py-3 text-right">
                <button
                  onClick={() => handleSort('answered')}
                  className="flex items-center justify-end space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  {renderSortLabel('answered', 'Answered')}
                </button>
              </th>
              <th className="bg-gray-50 px-6 py-3 text-right">
                <button
                  onClick={() => handleSort('abandoned')}
                  className="flex items-center justify-end space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  {renderSortLabel('abandoned', 'Abandoned')}
                </button>
              </th>
              <th className="bg-gray-50 px-6 py-3 text-right">
                <button
                  onClick={() => handleSort('answer_rate')}
                  className="flex items-center justify-end space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  {renderSortLabel('answer_rate', 'Answer Rate (%)')}
                </button>
              </th>
              <th className="bg-gray-50 px-6 py-3 text-right">
                <button
                  onClick={() => handleSort('service_level_30')}
                  className="flex items-center justify-end space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  {renderSortLabel('service_level_30', 'SL 30 (%)')}
                </button>
              </th>
              <th className="bg-gray-50 px-6 py-3 text-right">
                <button
                  onClick={() => handleSort('asa_sec')}
                  className="flex items-center justify-end space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  {renderSortLabel('asa_sec', 'ASA (sec)')}
                </button>
              </th>
              <th className="bg-gray-50 px-6 py-3 text-right">
                <button
                  onClick={() => handleSort('aht_sec')}
                  className="flex items-center justify-end space-x-2 font-semibold text-gray-900 hover:text-gray-700"
                >
                  {renderSortLabel('aht_sec', 'AHT (sec)')}
                </button>
              </th>
            </tr>
          </thead>

          {/* Body */}
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={8} className="py-8 text-center">
                  <div className="flex items-center justify-center space-x-2">
                    <div className="h-6 w-6 animate-spin rounded-full border-2 border-blue-300 border-t-blue-600"></div>
                    <span className="text-gray-600">Loading report...</span>
                  </div>
                </td>
              </tr>
            ) : displayData.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-8 text-center">
                  <AlertCircle className="mx-auto mb-2 text-gray-400" size={32} />
                  <p className="text-gray-600">No queue data available for the selected date range</p>
                </td>
              </tr>
            ) : (
              displayData.map((row) => {
                const answerRate =
                  row.offered > 0
                    ? ((row.answered / row.offered) * 100).toFixed(2)
                    : '0';

                return (
                  <tr
                    key={row.queue_id}
                    className="border-b border-gray-200 hover:bg-gray-50"
                  >
                    <td className="px-6 py-4 text-gray-900 font-medium">
                      {row.queue_name}
                    </td>
                    <td className="px-6 py-4 text-right text-gray-900">
                      {row.offered}
                    </td>
                    <td className="px-6 py-4 text-right text-gray-900">
                      {row.answered}
                    </td>
                    <td className="px-6 py-4 text-right text-gray-900">
                      {row.abandoned}
                    </td>
                    <td className="px-6 py-4 text-right text-gray-900">
                      {answerRate}%
                    </td>
                    <td className="px-6 py-4 text-right text-gray-900">
                      {row.service_level_30.toFixed(2)}%
                    </td>
                    <td className="px-6 py-4 text-right text-gray-900">
                      {row.asa_sec.toFixed(2)}
                    </td>
                    <td className="px-6 py-4 text-right text-gray-900">
                      {row.aht_sec.toFixed(2)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>

          {/* Footer - Totals Row */}
          {!loading && displayData.length > 0 && (
            <tfoot>
              <tr className="border-t-2 border-gray-300 bg-gray-50 font-semibold">
                <td className="px-6 py-4 text-gray-900">TOTAL</td>
                <td className="px-6 py-4 text-right text-gray-900">
                  {totals.offered}
                </td>
                <td className="px-6 py-4 text-right text-gray-900">
                  {totals.answered}
                </td>
                <td className="px-6 py-4 text-right text-gray-900">
                  {totals.abandoned}
                </td>
                <td className="px-6 py-4 text-right text-gray-900">
                  {totals.offered > 0
                    ? ((totals.answered / totals.offered) * 100).toFixed(2)
                    : '0'}
                  %
                </td>
                <td className="px-6 py-4 text-right text-gray-900">
                  {totals.service_level_30.toFixed(2)}%
                </td>
                <td className="px-6 py-4 text-right text-gray-900">
                  {totals.asa_sec.toFixed(2)}
                </td>
                <td className="px-6 py-4 text-right text-gray-900">
                  {totals.aht_sec.toFixed(2)}
                </td>
              </tr>
            </tfoot>
          )}
        </table>
      </div>

      {/* Info */}
      {data && !loading && (
        <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
          <div className="flex items-start space-x-3">
            <AlertCircle className="mt-1 flex-shrink-0 text-blue-600" size={20} />
            <div className="text-sm text-blue-800">
              <p className="font-semibold mb-1">Queue Entry Attribution</p>
              <p>
                Each row is based on unique queue entries (caller + join time), matching the dashboard KPIs.
                Transfers that re-enter a queue are counted as new queue entries.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
