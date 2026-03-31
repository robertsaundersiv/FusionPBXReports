import { create } from 'zustand';
import type { DashboardFilters, DateRange } from '../types';
import { dateUtils } from '../utils/formatters';

function getBrowserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Phoenix';
  } catch {
    return 'America/Phoenix';
  }
}

interface FilterStore {
  filters: DashboardFilters;
  updateDateRange: (range: DateRange) => void;
  updateQueueIds: (queueIds: string[]) => void;
  updateAgentUuids: (agentUuids: string[]) => void;
  updateTimezone: (timezone: string) => void;
  updateDirection: (direction?: 'inbound' | 'outbound' | 'local') => void;
  updateBusinessHoursOnly: (businessHoursOnly: boolean) => void;
  updateIncludeOutbound: (includeOutbound: boolean) => void;
  updateExcludeDeflects: (excludeDeflects: boolean) => void;
  updateStrictQueueAnswered: (strictQueueAnswered: boolean) => void;
  resetFilters: () => void;
}

const defaultFilters: DashboardFilters = {
  dateRange: {
    preset: 'today',
    ...dateUtils.getDateRangeByPreset('today'),
  },
  queueIds: [],
  agentUuids: [],
  businessHoursOnly: false,
  includeOutbound: false,
  excludeDeflects: true,
  strictQueueAnswered: false,
  timezone: getBrowserTimeZone(),
};

export const useFilterStore = create<FilterStore>((set) => ({
  filters: defaultFilters,

  updateDateRange: (range: DateRange) =>
    set((state) => ({
      filters: {
        ...state.filters,
        dateRange: range,
      },
    })),

  updateQueueIds: (queueIds: string[]) =>
    set((state) => ({
      filters: {
        ...state.filters,
        queueIds,
      },
    })),

  updateAgentUuids: (agentUuids: string[]) =>
    set((state) => ({
      filters: {
        ...state.filters,
        agentUuids,
      },
    })),

  updateTimezone: (timezone: string) =>
    set((state) => ({
      filters: {
        ...state.filters,
        timezone,
      },
    })),

  updateDirection: (direction?: 'inbound' | 'outbound' | 'local') =>
    set((state) => ({
      filters: {
        ...state.filters,
        direction,
      },
    })),

  updateBusinessHoursOnly: (businessHoursOnly: boolean) =>
    set((state) => ({
      filters: {
        ...state.filters,
        businessHoursOnly,
      },
    })),

  updateIncludeOutbound: (includeOutbound: boolean) =>
    set((state) => ({
      filters: {
        ...state.filters,
        includeOutbound,
      },
    })),

  updateExcludeDeflects: (excludeDeflects: boolean) =>
    set((state) => ({
      filters: {
        ...state.filters,
        excludeDeflects,
      },
    })),

  updateStrictQueueAnswered: (strictQueueAnswered: boolean) =>
    set((state) => ({
      filters: {
        ...state.filters,
        strictQueueAnswered,
      },
    })),

  resetFilters: () => set({ filters: defaultFilters }),
}));
