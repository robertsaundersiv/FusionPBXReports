import { useState, useEffect, useMemo } from 'react';
import { useFilterStore } from '../hooks/useFilterStore';
import DashboardFilterBar from '../components/DashboardFilterBar';
import QueuePerformanceCard from '../components/QueuePerformanceCard';
import { dashboardService } from '../services/dashboard';
import {
  groupQueuesByPrefix,
  generateHourlyTimeline,
  fillMissingHourlyBuckets,
} from '../utils/queuePerformance';
import type {
  QueuePerformanceHourlyData,
  QueuePerformanceHourlyResponse,
  Queue,
  Agent,
  GroupedQueue,
} from '../types';
import { ChevronDown, ChevronUp, AlertCircle, RefreshCw } from 'lucide-react';

export default function QueuePerformance() {
  const { filters, updateDateRange, updateQueueIds, updateDirection } = useFilterStore();
  const [data, setData] = useState<QueuePerformanceHourlyResponse | null>(null);
  const [queues, setQueues] = useState<Queue[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set());

  // Load data when filters change
  useEffect(() => {
    loadData();
  }, [filters]);

  // Load metadata on mount
  useEffect(() => {
    loadMetadata();
  }, []);

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

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      console.log('📊 Loading Queue Performance data with filters:', filters);
      const response = await dashboardService.getQueuePerformance(filters);
      console.log('📈 Queue Performance Response:', response);

      // Process hourly data - fill missing buckets
      if (response.queues && Array.isArray(response.queues)) {
        const timeline = generateHourlyTimeline(
          filters.dateRange.startDate!,
          filters.dateRange.endDate!
        );

        const processedQueues = response.queues.map((queue: QueuePerformanceHourlyData) => ({
          ...queue,
          hourly: fillMissingHourlyBuckets(queue.hourly || [], timeline),
        }));

        setData({ queues: processedQueues });
      } else {
        setData(response);
      }

      setLastUpdated(new Date());
      setLoading(false);
    } catch (err: any) {
      console.error('Error loading queue performance data:', err);
      setError(err.message || 'Failed to load queue performance data');
      setLoading(false);
    }
  };

  const handleRetry = () => {
    loadData();
  };

  // Group queues by prefix
  const groupedQueues: GroupedQueue[] = useMemo(() => {
    if (!data || !data.queues || data.queues.length === 0) {
      return [];
    }
    const groups = groupQueuesByPrefix(data.queues);
    
    // Auto-expand all groups by default on first load
    if (expandedGroups.size === 0 && groups.length > 0) {
      const allKeys = new Set(groups.map(g => g.groupKey));
      setExpandedGroups(allKeys);
    }
    
    return groups;
  }, [data]);

  const toggleGroup = (groupKey: string) => {
    const newExpanded = new Set(expandedGroups);
    if (newExpanded.has(groupKey)) {
      newExpanded.delete(groupKey);
    } else {
      newExpanded.add(groupKey);
    }
    setExpandedGroups(newExpanded);
  };

  const toggleAllGroups = () => {
    if (expandedGroups.size === groupedQueues.length) {
      // Collapse all
      setExpandedGroups(new Set());
    } else {
      // Expand all
      setExpandedGroups(new Set(groupedQueues.map(g => g.groupKey)));
    }
  };

  // Loading state
  if (loading) {
    return (
      <div className="overflow-auto">
        <DashboardFilterBar
          filters={filters}
          queues={queues}
          agents={agents}
          onFiltersChange={(newFilters) => {
            updateDateRange(newFilters.dateRange);
            updateQueueIds(newFilters.queueIds);
            updateDirection(newFilters.direction);
          }}
        />
        <div className="p-8 text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <p className="mt-3 text-gray-600">Loading Queue Performance...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="overflow-auto">
        <DashboardFilterBar
          filters={filters}
          queues={queues}
          agents={agents}
          onFiltersChange={(newFilters) => {
            updateDateRange(newFilters.dateRange);
            updateQueueIds(newFilters.queueIds);
            updateDirection(newFilters.direction);
          }}
        />
        <div className="p-8">
          <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-2xl mx-auto">
            <div className="flex items-center mb-3">
              <AlertCircle className="text-red-600 mr-2" size={24} />
              <h3 className="text-lg font-semibold text-red-900">Error Loading Data</h3>
            </div>
            <p className="text-red-700 mb-4">{error}</p>
            <button
              onClick={handleRetry}
              className="flex items-center px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            >
              <RefreshCw size={16} className="mr-2" />
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Empty state
  if (!data || !data.queues || data.queues.length === 0) {
    return (
      <div className="overflow-auto">
        <DashboardFilterBar
          filters={filters}
          queues={queues}
          agents={agents}
          onFiltersChange={(newFilters) => {
            updateDateRange(newFilters.dateRange);
            updateQueueIds(newFilters.queueIds);
            updateDirection(newFilters.direction);
          }}
        />
        <div className="p-8">
          <div className="bg-gray-50 border border-gray-200 rounded-lg p-8 max-w-2xl mx-auto text-center">
            <AlertCircle className="text-gray-400 mx-auto mb-3" size={48} />
            <h3 className="text-lg font-semibold text-gray-900 mb-2">No Data Available</h3>
            <p className="text-gray-600">
              No queue performance data found for the selected filters. Try adjusting your date range or queue selection.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-auto">
      {/* Filter Bar */}
      <DashboardFilterBar
        filters={filters}
        queues={queues}
        agents={agents}
        onFiltersChange={(newFilters) => {
          updateDateRange(newFilters.dateRange);
          updateQueueIds(newFilters.queueIds);
          updateDirection(newFilters.direction);
        }}
      />

      {/* Main Content */}
      <div className="p-6 space-y-6">
        {/* Page Header */}
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Queue Performance</h1>
            <p className="text-sm text-gray-500 mt-1">
              Hourly bucketed performance metrics by queue
            </p>
          </div>
          <div className="text-right">
            {lastUpdated && (
              <p className="text-xs text-gray-500">
                Last updated: {lastUpdated.toLocaleTimeString()}
              </p>
            )}
            <button
              onClick={toggleAllGroups}
              className="mt-1 text-sm text-blue-600 hover:text-blue-800 font-medium"
            >
              {expandedGroups.size === groupedQueues.length ? 'Collapse All' : 'Expand All'}
            </button>
          </div>
        </div>

        {/* Summary Stats */}
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-sm font-medium text-blue-900">
                Showing {data.queues.length} queue{data.queues.length !== 1 ? 's' : ''} 
                {' '}in {groupedQueues.length} group{groupedQueues.length !== 1 ? 's' : ''}
              </span>
            </div>
            <div className="text-sm text-blue-700">
              Date Range: {filters.dateRange.startDate?.toLocaleDateString()} - {filters.dateRange.endDate?.toLocaleDateString()}
            </div>
          </div>
        </div>

        {/* Grouped Queue Cards */}
        {groupedQueues.map((group) => (
          <div key={group.groupKey} className="space-y-4">
            {/* Group Header */}
            <div
              className="flex items-center justify-between bg-gray-100 px-4 py-3 rounded-lg cursor-pointer hover:bg-gray-200 transition-colors"
              onClick={() => toggleGroup(group.groupKey)}
            >
              <div className="flex items-center">
                <span className="text-lg font-bold text-gray-900 mr-3">{group.groupKey}</span>
                <span className="px-2.5 py-0.5 bg-gray-700 text-white text-xs font-medium rounded-full">
                  {group.queues.length} queue{group.queues.length !== 1 ? 's' : ''}
                </span>
              </div>
              <div>
                {expandedGroups.has(group.groupKey) ? (
                  <ChevronUp size={20} className="text-gray-600" />
                ) : (
                  <ChevronDown size={20} className="text-gray-600" />
                )}
              </div>
            </div>

            {/* Queue Cards Grid (only when expanded) */}
            {expandedGroups.has(group.groupKey) && (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
                {group.queues.map((queue) => (
                  <QueuePerformanceCard
                    key={queue.queue_id}
                    queueData={queue}
                    groupPrefix={group.groupKey}
                  />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}