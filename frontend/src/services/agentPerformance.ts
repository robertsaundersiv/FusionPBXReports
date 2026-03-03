import apiClient from './api';
import type {
  DashboardFilters,
  AgentLeaderboardResponse,
  AgentTrendsResponse,
  AgentOutliersResponse,
  AgentCallsResponse,
  AgentCallDetail,
  AgentPerformanceReportResponse,
} from '../types';

function formatAgentParams(filters: DashboardFilters) {
  const params: Record<string, any> = {};

  if (filters.dateRange?.startDate) {
    params.start = filters.dateRange.startDate instanceof Date
      ? filters.dateRange.startDate.toISOString()
      : filters.dateRange.startDate;
  }
  if (filters.dateRange?.endDate) {
    params.end = filters.dateRange.endDate instanceof Date
      ? filters.dateRange.endDate.toISOString()
      : filters.dateRange.endDate;
  }

  if (filters.queueIds && filters.queueIds.length > 0) {
    params.queues = filters.queueIds.join(',');
  }

  if (filters.agentUuids && filters.agentUuids.length > 0) {
    params.agents = filters.agentUuids.join(',');
  }

  params.include_outbound = filters.includeOutbound;
  params.exclude_deflects = filters.excludeDeflects;

  return params;
}

export const agentPerformanceService = {
  async getLeaderboard(filters: DashboardFilters): Promise<AgentLeaderboardResponse> {
    const response = await apiClient.get('/api/v1/agent-performance/leaderboard', {
      params: formatAgentParams(filters),
    });
    return response.data;
  },

  async getTrends(filters: DashboardFilters, agentId: string): Promise<AgentTrendsResponse> {
    const response = await apiClient.get('/api/v1/agent-performance/trends', {
      params: {
        ...formatAgentParams(filters),
        agent_id: agentId,
        bucket: 'hour',
      },
    });
    return response.data;
  },

  async getOutliers(
    filters: DashboardFilters,
    agentId: string,
    type: 'long_calls' | 'low_mos',
    limit: number = 50
  ): Promise<AgentOutliersResponse> {
    const response = await apiClient.get('/api/v1/agent-performance/outliers', {
      params: {
        ...formatAgentParams(filters),
        agent_id: agentId,
        type,
        limit,
      },
    });
    return response.data;
  },

  async getCalls(
    filters: DashboardFilters,
    agentId: string,
    options: {
      limit?: number;
      offset?: number;
      sort?: 'start_epoch' | 'billsec' | 'mos';
      order?: 'asc' | 'desc';
      search?: string;
      hangupCause?: string;
      missedOnly?: boolean;
    } = {}
  ): Promise<AgentCallsResponse> {
    const response = await apiClient.get('/api/v1/agent-performance/calls', {
      params: {
        ...formatAgentParams(filters),
        agent_id: agentId,
        limit: options.limit ?? 50,
        offset: options.offset ?? 0,
        sort: options.sort ?? 'start_epoch',
        order: options.order ?? 'desc',
        search: options.search || undefined,
        hangup_cause: options.hangupCause || undefined,
        missed_only: options.missedOnly || false,
      },
    });
    return response.data;
  },

  async getCallDetail(callId: string): Promise<AgentCallDetail> {
    const response = await apiClient.get(`/api/v1/agent-performance/calls/${callId}`);
    return response.data;
  },

  async getReport(filters: DashboardFilters): Promise<AgentPerformanceReportResponse> {
    const response = await apiClient.get('/api/v1/agent-performance/report', {
      params: formatAgentParams(filters),
    });
    return response.data;
  },
};
