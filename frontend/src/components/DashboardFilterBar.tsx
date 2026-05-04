import { useMemo, useState } from 'react';
import { DashboardFilters } from '../types';
import { Filter, Search } from 'lucide-react';
import { endOfDay, format, startOfDay } from 'date-fns';
import { dateUtils } from '../utils/formatters';

function getBrowserTimeZone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Phoenix';
  } catch {
    return 'America/Phoenix';
  }
}

function getUtcDateRangeByPreset(preset: string): { startDate: Date; endDate: Date } {
  const now = new Date();
  const y = now.getUTCFullYear();
  const m = now.getUTCMonth();
  const d = now.getUTCDate();

  const makeStart = (daysBack: number) => new Date(Date.UTC(y, m, d - daysBack, 0, 0, 0, 0));
  const makeEnd = (daysBack: number) => new Date(Date.UTC(y, m, d - daysBack, 23, 59, 59, 999));

  switch (preset) {
    case 'today':
      return { startDate: makeStart(0), endDate: makeEnd(0) };
    case 'yesterday':
      return { startDate: makeStart(1), endDate: makeEnd(1) };
    case 'last_7':
      return { startDate: makeStart(6), endDate: makeEnd(0) };
    case 'last_30':
      return { startDate: makeStart(29), endDate: makeEnd(0) };
    default:
      return { startDate: makeStart(0), endDate: makeEnd(0) };
  }
}

interface DashboardFilterBarProps {
  filters: DashboardFilters;
  queues: Array<{ id: number; queue_id: string; name: string }>;
  agents: Array<{
    agent_uuid?: string;
    agent_id?: string | number;
    id?: number;
    agent_name: string;
  }>;
  onFiltersChange: (filters: DashboardFilters) => void;
  showQueues?: boolean;
  showAgents?: boolean;
  showDirection?: boolean;
  showOutboundToggle?: boolean;
  showExcludeDeflectsToggle?: boolean;
  showStrictQueueAnsweredToggle?: boolean;
  outboundBadgeText?: string;
}

export default function DashboardFilterBar({
  filters,
  queues,
  agents,
  onFiltersChange,
  showQueues = true,
  showAgents = false,
  showDirection = true,
  showOutboundToggle = false,
  showExcludeDeflectsToggle = false,
  showStrictQueueAnsweredToggle = false,
  outboundBadgeText,
}: DashboardFilterBarProps) {
  const datePresets = ['today', 'yesterday', 'last_7', 'last_30', 'custom'];
  const localTimeZone = getBrowserTimeZone();
  const isUtcMode = filters.timezone === 'UTC';
  const [agentSearchTerm, setAgentSearchTerm] = useState('');
  const [queueSearchTerm, setQueueSearchTerm] = useState('');

  const getPresetDateRange = (preset: string) =>
    isUtcMode ? getUtcDateRangeByPreset(preset) : dateUtils.getDateRangeByPreset(preset);

  const normalizedAgentSearchTerm = agentSearchTerm.trim().toLowerCase();

  const sortedAgents = useMemo(
    () => [...agents].sort((a, b) => a.agent_name.localeCompare(b.agent_name)),
    [agents]
  );

  const filteredAgents = useMemo(
    () =>
      sortedAgents.filter((agent) => {
        if (!normalizedAgentSearchTerm) {
          return true;
        }

        return agent.agent_name.toLowerCase().includes(normalizedAgentSearchTerm);
      }),
    [normalizedAgentSearchTerm, sortedAgents]
  );

  const normalizedQueueSearchTerm = queueSearchTerm.trim().toLowerCase();

  const sortedQueues = useMemo(
    () =>
      [...queues].sort((a, b) => {
        const nameA = (a.name || '').toLowerCase();
        const nameB = (b.name || '').toLowerCase();
        return nameA.localeCompare(nameB);
      }),
    [queues]
  );

  const filteredQueues = useMemo(
    () =>
      sortedQueues.filter((queue) => {
        if (!normalizedQueueSearchTerm) {
          return true;
        }

        const queueName = (queue.name || '').toLowerCase();
        return queueName.includes(normalizedQueueSearchTerm);
      }),
    [normalizedQueueSearchTerm, sortedQueues]
  );

  const handleDatePresetChange = (preset: string) => {
    if (preset === 'custom') {
      const fallbackStart = startOfDay(new Date());
      const fallbackEnd = endOfDay(new Date());
      onFiltersChange({
        ...filters,
        dateRange: {
          preset: 'custom',
          startDate: filters.dateRange.startDate ?? fallbackStart,
          endDate: filters.dateRange.endDate ?? fallbackEnd,
        },
      });
      return;
    }

    const { startDate, endDate } = getPresetDateRange(preset);
    onFiltersChange({
      ...filters,
      dateRange: {
        preset: preset as any,
        startDate,
        endDate,
      },
    });
  };

  const formatDateInputValue = (date?: Date) => (date ? format(date, 'yyyy-MM-dd') : '');

  const parseDateInputValue = (value: string) => {
    if (!value) return null;
    const [year, month, day] = value.split('-').map(Number);
    if (!year || !month || !day) return null;
    if (isUtcMode) {
      return new Date(Date.UTC(year, month - 1, day, 0, 0, 0, 0));
    }
    return new Date(year, month - 1, day);
  };

  const asStartOfSelectedDay = (date: Date) =>
    isUtcMode
      ? new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), 0, 0, 0, 0))
      : startOfDay(date);

  const asEndOfSelectedDay = (date: Date) =>
    isUtcMode
      ? new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate(), 23, 59, 59, 999))
      : endOfDay(date);

  const handleCustomDateChange = (value: string, field: 'start' | 'end') => {
    const parsed = parseDateInputValue(value);
    if (!parsed) return;

    if (field === 'start') {
      const newStart = asStartOfSelectedDay(parsed);
      let newEnd = filters.dateRange.endDate ? asEndOfSelectedDay(filters.dateRange.endDate) : asEndOfSelectedDay(parsed);
      if (newEnd < newStart) {
        newEnd = asEndOfSelectedDay(parsed);
      }
      onFiltersChange({
        ...filters,
        dateRange: {
          preset: 'custom',
          startDate: newStart,
          endDate: newEnd,
        },
      });
      return;
    }

    const newEnd = asEndOfSelectedDay(parsed);
    let newStart = filters.dateRange.startDate ? asStartOfSelectedDay(filters.dateRange.startDate) : asStartOfSelectedDay(parsed);
    if (newStart > newEnd) {
      newStart = asStartOfSelectedDay(parsed);
    }
    onFiltersChange({
      ...filters,
      dateRange: {
        preset: 'custom',
        startDate: newStart,
        endDate: newEnd,
      },
    });
  };

  const handleTimezoneModeToggle = (useUtc: boolean) => {
    const timezone = useUtc ? 'UTC' : localTimeZone;
    const updatedFilters: DashboardFilters = {
      ...filters,
      timezone,
    };

    if (filters.dateRange.preset !== 'custom') {
      const presetRange = useUtc
        ? getUtcDateRangeByPreset(filters.dateRange.preset)
        : dateUtils.getDateRangeByPreset(filters.dateRange.preset);
      updatedFilters.dateRange = {
        ...updatedFilters.dateRange,
        ...presetRange,
      };
    }

    onFiltersChange(updatedFilters);
  };


  return (
    <div className="bg-white border-b border-gray-200 p-4 space-y-4">
      <div className="flex items-center space-x-2">
        <Filter size={20} className="text-gray-600" />
        <span className="font-semibold text-gray-900">Filters</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Date Range */}
        <div className="space-y-2">
          <label className="block text-sm font-medium text-gray-700">Date Range</label>
          <div className="flex flex-wrap gap-2">
            {datePresets.map((preset) => (
              <button
                key={preset}
                onClick={() => handleDatePresetChange(preset)}
                className={`px-3 py-1 rounded text-sm font-medium transition-colors ${
                  filters.dateRange.preset === preset
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
              >
                {preset === 'last_7' ? 'Last 7 days' : 
                 preset === 'last_30' ? 'Last 30 days' : 
                 preset === 'custom' ? 'Custom' :
                 preset.charAt(0).toUpperCase() + preset.slice(1)}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <label className="block text-xs font-medium text-gray-600">Start date</label>
              <input
                type="date"
                value={formatDateInputValue(filters.dateRange.startDate)}
                onChange={(e) => handleCustomDateChange(e.target.value, 'start')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600">End date</label>
              <input
                type="date"
                value={formatDateInputValue(filters.dateRange.endDate)}
                onChange={(e) => handleCustomDateChange(e.target.value, 'end')}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
              />
            </div>
          </div>
        </div>

        {/* Queues */}
        {showQueues && (
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700">
              Queues {filters.queueIds.length > 0 && `(${filters.queueIds.length} selected)`}
            </label>
            <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">
              Find queue in list
            </label>
            <div className="relative">
              <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={queueSearchTerm}
                onChange={(e) => setQueueSearchTerm(e.target.value)}
                placeholder="Type a queue name to filter the list"
                aria-label="Search queues list"
                autoComplete="off"
                className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm"
              />
            </div>
            <select
              multiple
              size={4}
              value={filters.queueIds}
              onChange={(e) => {
                const visibleSelected = Array.from(e.target.selectedOptions, (option) => option.value);
                // Build set of values currently visible in the filtered list
                const visibleValueSet = new Set(
                  filteredQueues
                    .map((q) => String(q.queue_id))
                    .filter(Boolean) as string[]
                );
                // Keep selections for queues hidden by the current search term
                const hiddenSelected = filters.queueIds.filter((id) => !visibleValueSet.has(id));
                onFiltersChange({ ...filters, queueIds: [...hiddenSelected, ...visibleSelected] });
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            >
              {filteredQueues.map((queue) => (
                <option key={queue.queue_id} value={String(queue.queue_id)}>
                  {queue.name || queue.queue_id}
                </option>
              ))}
            </select>
            <p className="text-xs text-gray-500">Hold Ctrl/Cmd to select multiple. None = All queues</p>
          </div>
        )}

        {/* Agents */}
        {showAgents && (
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700">
              Agents {filters.agentUuids.length > 0 && `(${filters.agentUuids.length} selected)`}
            </label>
            <label className="block text-xs font-medium uppercase tracking-wide text-gray-500">
              Find agent in list
            </label>
            <div className="relative">
              <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <input
                type="text"
                value={agentSearchTerm}
                onChange={(e) => setAgentSearchTerm(e.target.value)}
                placeholder="Type an agent name to filter the list"
                aria-label="Search agents list"
                autoComplete="off"
                className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm"
              />
            </div>
            <select
              multiple
              size={4}
              value={filters.agentUuids}
              onChange={(e) => {
                const visibleSelected = Array.from(e.target.selectedOptions, (option) => option.value);
                // Build set of values currently visible in the filtered list
                const visibleValueSet = new Set(
                  filteredAgents
                    .map((a) =>
                      a.agent_uuid ||
                      (a.agent_id !== undefined ? String(a.agent_id) : undefined) ||
                      (a.id !== undefined ? String(a.id) : undefined)
                    )
                    .filter(Boolean) as string[]
                );
                // Keep selections for agents hidden by the current search term
                const hiddenSelected = filters.agentUuids.filter((id) => !visibleValueSet.has(id));
                onFiltersChange({ ...filters, agentUuids: [...hiddenSelected, ...visibleSelected] });
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            >
              {filteredAgents
                .map((agent, index) => {
                  const agentValue =
                    agent.agent_uuid ||
                    (agent.agent_id !== undefined ? String(agent.agent_id) : undefined) ||
                    (agent.id !== undefined ? String(agent.id) : undefined);

                  if (!agentValue) {
                    return null;
                  }

                  return (
                    <option key={agentValue || `agent-${index}-${agent.agent_name}`} value={agentValue}>
                      {agent.agent_name}
                    </option>
                  );
                })
                .filter(Boolean)}
            </select>
            <p className="text-xs text-gray-500">
              Hold Ctrl/Cmd to select multiple. None = All agents
              {normalizedAgentSearchTerm ? ` • ${filteredAgents.length} match${filteredAgents.length === 1 ? '' : 'es'}` : ''}
            </p>
          </div>
        )}

        {/* Direction */}
        {showDirection && (
          <div className="space-y-2">
            <label className="block text-sm font-medium text-gray-700">Direction</label>
            <select
              value={filters.direction || ''}
              onChange={(e) =>
                onFiltersChange({
                  ...filters,
                  direction: (e.target.value || undefined) as any,
                })
              }
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            >
              <option value="">All Directions</option>
              <option value="inbound">Inbound</option>
              <option value="outbound">Outbound</option>
              <option value="local">Local</option>
            </select>
          </div>
        )}
      </div>

      {(showOutboundToggle || showExcludeDeflectsToggle || showStrictQueueAnsweredToggle) && (
        <div className="flex flex-wrap gap-4">
          {showOutboundToggle && (
            <div className="relative flex items-center gap-2">
              <label className="flex items-center gap-2 text-sm text-gray-700">
                <input
                  type="checkbox"
                  checked={filters.includeOutbound}
                  onChange={(e) => onFiltersChange({ ...filters, includeOutbound: e.target.checked })}
                />
                Include outbound
              </label>
              {filters.includeOutbound && outboundBadgeText && (
                <span className="inline-flex items-center rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-semibold text-emerald-700 shadow-sm">
                  {outboundBadgeText}
                </span>
              )}
            </div>
          )}
          {showExcludeDeflectsToggle && (
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={filters.excludeDeflects}
                onChange={(e) => onFiltersChange({ ...filters, excludeDeflects: e.target.checked })}
              />
              Exclude voicemail/external deflects
            </label>
          )}
          {showStrictQueueAnsweredToggle && (
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={filters.strictQueueAnswered}
                onChange={(e) => onFiltersChange({ ...filters, strictQueueAnswered: e.target.checked })}
              />
              Strict queue answered mode
            </label>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3 text-sm text-gray-700">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={isUtcMode}
            onChange={(e) => handleTimezoneModeToggle(e.target.checked)}
          />
          Use UTC timezone
        </label>
        <span className="text-xs text-gray-500">
          Current: {filters.timezone}
        </span>
      </div>
    </div>
  );
}
