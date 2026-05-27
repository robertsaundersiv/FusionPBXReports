import apiClient from './api';
import type { ExecutiveOverviewData, DashboardFilters } from '../types';
import { dateUtils } from '../utils/formatters';

interface QueueReportPrefetchOptions {
  timezone?: string;
}

interface PrefetchRange {
  start: Date;
  end: Date;
}

function getBrowserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Phoenix';
  } catch {
    return 'America/Phoenix';
  }
}

function buildQueueReportPrefetchRanges() {
  // Match DashboardFilterBar presets exactly so prefetch hits the same cache keys.
  return ['last_7', 'last_30', 'today', 'yesterday'].map((preset) => {
    const range = dateUtils.getDateRangeByPreset(preset);
    return {
      start: range.startDate,
      end: range.endDate,
    };
  });
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function prefetchExecutiveOverviewRange(range: PrefetchRange, timezone: string): Promise<void> {
  return apiClient
    .get('/api/v1/dashboard/executive-overview', {
      params: {
        start_date: range.start.toISOString(),
        end_date: range.end.toISOString(),
        direction: 'inbound',
        timezone,
      },
    })
    .then(() => undefined)
    .catch(() => undefined);
}

function prefetchQueueReportRange(range: PrefetchRange, timezone: string): Promise<void> {
  return apiClient
    .get('/api/v1/dashboard/queue-performance-report', {
      params: {
        start_date: range.start.toISOString(),
        end_date: range.end.toISOString(),
        direction: 'inbound',
        exclude_deflects: true,
        timezone,
      },
    })
    .then(() => undefined)
    .catch(() => undefined);
}

function prefetchAgentReportRange(range: PrefetchRange): Promise<void> {
  return apiClient
    .get('/api/v1/agent-performance/report', {
      params: {
        start: range.start.toISOString(),
        end: range.end.toISOString(),
        include_outbound: false,
        exclude_deflects: true,
      },
    })
    .then(() => undefined)
    .catch(() => undefined);
}

// Helper function to convert frontend filters to backend API params
function formatFiltersForAPI(filters: DashboardFilters) {
  const params: any = {};
  
  // Convert date range - ensure dates are ISO strings
  if (filters.dateRange?.startDate) {
    params.start_date = filters.dateRange.startDate instanceof Date 
      ? filters.dateRange.startDate.toISOString()
      : filters.dateRange.startDate;
  }
  if (filters.dateRange?.endDate) {
    params.end_date = filters.dateRange.endDate instanceof Date
      ? filters.dateRange.endDate.toISOString()
      : filters.dateRange.endDate;
  }
  
  // Convert queue IDs - only send if not empty
  if (filters.queueIds && filters.queueIds.length > 0) {
    params.queue_ids = filters.queueIds;
  }
  
  // Convert agent UUIDs - only send if not empty
  if (filters.agentUuids && filters.agentUuids.length > 0) {
    params.agent_uuids = filters.agentUuids;
  }
  
  // Add direction if specified
  if (filters.direction) {
    params.direction = filters.direction;
  }
  
  // Add business hours flag if true
  if (filters.businessHoursOnly) {
    params.business_hours_only = true;
  }

  if (filters.timezone) {
    params.timezone = filters.timezone;
  }
  
  console.log('Sending API request with params:', params);
  
  return params;
}

export const dashboardService = {
  prefetchCommonQueueReportViews(options: QueueReportPrefetchOptions = {}) {
    const timezone = options.timezone || getBrowserTimeZone();
    const ranges = buildQueueReportPrefetchRanges();

    // Stagger requests to avoid a single burst right after login.
    ranges.forEach((range, idx) => {
      window.setTimeout(() => {
        void apiClient
          .get('/api/v1/dashboard/queue-performance-report', {
            params: {
              start_date: range.start.toISOString(),
              end_date: range.end.toISOString(),
              direction: 'inbound',
              exclude_deflects: true,
              timezone,
            },
          })
          .catch(() => {
            // Prefetch is best-effort; ignore failures.
          });
      }, idx * 350);
    });
  },

  prefetchPostLoginViews(options: QueueReportPrefetchOptions = {}) {
    const timezone = options.timezone || getBrowserTimeZone();
    const ranges = buildQueueReportPrefetchRanges();
    const executiveRanges = ranges.slice(0, 2); // last_7, last_30

    void (async () => {
      // Requested order: Executive -> Queue Performance Report -> Agent Performance Report.
      for (const range of executiveRanges) {
        await prefetchExecutiveOverviewRange(range, timezone);
        await sleep(150);
      }

      for (const range of ranges) {
        await prefetchQueueReportRange(range, timezone);
        await sleep(150);
      }

      for (const range of ranges) {
        await prefetchAgentReportRange(range);
        await sleep(150);
      }
    })();
  },

  async getExecutiveOverview(filters: DashboardFilters): Promise<ExecutiveOverviewData> {
    const params = formatFiltersForAPI(filters);
    console.log('📊 Requesting Executive Overview with params:', params);
    console.log('Queue IDs being sent:', filters.queueIds);
    
    const response = await apiClient.get('/api/v1/dashboard/executive-overview', {
      params,
    });
    
    console.log('📈 Executive Overview Response:', response.data);
    console.log('Offered value:', response.data.offered?.value);
    console.log('Answer Rate:', response.data.answerRate?.value);
    
    return response.data;
  },

  async getQueuePerformance(filters: DashboardFilters, queueIds?: string[]) {
    const params = formatFiltersForAPI(filters);

    if (filters.strictQueueAnswered) {
      params.strict_answered = true;
    }
    
    // If specific queue IDs are provided for comparison, use those instead of filter queue IDs
    if (queueIds && queueIds.length > 0) {
      params.queue_ids = queueIds;
    }
    
    const response = await apiClient.get('/api/v1/dashboard/queue-performance', {
      params,
    });
    return response.data;
  },

  async getAgentPerformance(agentUuid: string, filters: DashboardFilters) {
    const response = await apiClient.get(`/api/v1/dashboard/agent-performance/${agentUuid}`, {
      params: filters,
    });
    return response.data;
  },

  async getQualityMetrics(filters: DashboardFilters) {
    const response = await apiClient.get('/api/v1/dashboard/quality', {
      params: filters,
    });
    return response.data;
  },

  async getRepeatCallers(filters: DashboardFilters) {
    const params = formatFiltersForAPI(filters);
    const response = await apiClient.get('/api/v1/dashboard/repeat-callers', {
      params,
    });
    return response.data;
  },

  async getCalls(filters: DashboardFilters, page: number = 1, limit: number = 50) {
    const response = await apiClient.get('/api/v1/cdr/calls', {
      params: {
        ...filters,
        page,
        limit,
      },
    });
    return response.data;
  },

  async getQueues() {
    const response = await apiClient.get('/api/v1/dashboard/queues-visible');
    return response.data;
  },

  async getAgents() {
    const response = await apiClient.get('/api/v1/dashboard/agents-visible');
    return response.data;
  },

  async getQueuePerformanceReport(filters: DashboardFilters) {
    const params: any = {};
    
    // Convert date range - ensure dates are ISO strings
    if (filters.dateRange?.startDate) {
      params.start_date = filters.dateRange.startDate instanceof Date 
        ? filters.dateRange.startDate.toISOString()
        : filters.dateRange.startDate;
    }
    if (filters.dateRange?.endDate) {
      params.end_date = filters.dateRange.endDate instanceof Date
        ? filters.dateRange.endDate.toISOString()
        : filters.dateRange.endDate;
    }
    
    // Convert queue IDs - only send if not empty
    if (filters.queueIds && filters.queueIds.length > 0) {
      params.queue_ids = filters.queueIds;
    }
    
    // Add exclude deflects flag
    if (filters.excludeDeflects !== undefined) {
      params.exclude_deflects = filters.excludeDeflects;
    }

    if (filters.direction) {
      params.direction = filters.direction;
    }

    if (filters.timezone) {
      params.timezone = filters.timezone;
    }

    if (filters.strictQueueAnswered) {
      params.strict_answered = true;
    }
    
    const response = await apiClient.get('/api/v1/dashboard/queue-performance-report', {
      params,
    });
    return response.data;
  },

  async getOutboundCalls(filters: DashboardFilters) {
    const params: any = {};
    
    // Convert date range - ensure dates are ISO strings
    if (filters.dateRange?.startDate) {
      params.start_date = filters.dateRange.startDate instanceof Date 
        ? filters.dateRange.startDate.toISOString()
        : filters.dateRange.startDate;
    }
    if (filters.dateRange?.endDate) {
      params.end_date = filters.dateRange.endDate instanceof Date
        ? filters.dateRange.endDate.toISOString()
        : filters.dateRange.endDate;
    }
    
    // Convert queue IDs - only send if not empty
    if (filters.queueIds && filters.queueIds.length > 0) {
      params.queue_ids = filters.queueIds;
    }

    const response = await apiClient.get('/api/v1/dashboard/outbound-calls', {
      params,
    });
    return response.data;
  },
};