import { DashboardFilters } from '../types';
import { Filter } from 'lucide-react';
import { endOfDay, format, startOfDay } from 'date-fns';
import { dateUtils } from '../utils/formatters';

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
}: DashboardFilterBarProps) {
  const datePresets = ['today', 'yesterday', 'last_7', 'last_30', 'custom'];

  // Sort agents alphabetically by name
  const sortedAgents = [...agents].sort((a, b) => 
    a.agent_name.localeCompare(b.agent_name)
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

    const { startDate, endDate } = dateUtils.getDateRangeByPreset(preset);
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
    return new Date(year, month - 1, day);
  };

  const handleCustomDateChange = (value: string, field: 'start' | 'end') => {
    const parsed = parseDateInputValue(value);
    if (!parsed) return;

    if (field === 'start') {
      const newStart = startOfDay(parsed);
      let newEnd = filters.dateRange.endDate ? endOfDay(filters.dateRange.endDate) : endOfDay(parsed);
      if (newEnd < newStart) {
        newEnd = endOfDay(parsed);
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

    const newEnd = endOfDay(parsed);
    let newStart = filters.dateRange.startDate ? startOfDay(filters.dateRange.startDate) : startOfDay(parsed);
    if (newStart > newEnd) {
      newStart = startOfDay(parsed);
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
          <select
            multiple
            size={4}
            value={filters.queueIds}
            onChange={(e) => {
              const selected = Array.from(e.target.selectedOptions, (option) => option.value);
              onFiltersChange({ ...filters, queueIds: selected });
            }}
            className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
          >
            {queues.map((queue) => (
              <option key={queue.queue_id} value={String(queue.queue_id)}>
                {queue.name || (queue as { queue_name?: string }).queue_name || queue.queue_id}
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
            <select
              multiple
              size={4}
              value={filters.agentUuids}
              onChange={(e) => {
                const selected = Array.from(e.target.selectedOptions, (option) => option.value);
                onFiltersChange({ ...filters, agentUuids: selected });
              }}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm"
            >
              {sortedAgents
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
            <p className="text-xs text-gray-500">Hold Ctrl/Cmd to select multiple. None = All agents</p>
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

      {(showOutboundToggle || showExcludeDeflectsToggle) && (
        <div className="flex flex-wrap gap-4">
          {showOutboundToggle && (
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={filters.includeOutbound}
                onChange={(e) => onFiltersChange({ ...filters, includeOutbound: e.target.checked })}
              />
              Include outbound
            </label>
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
        </div>
      )}
    </div>
  );
}
