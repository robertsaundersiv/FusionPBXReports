import { useCallback, useEffect, useMemo, useState } from 'react';
import { subDays } from 'date-fns';
import { dashboardService } from '../services/dashboard';
import { useFilterStore } from '../hooks/useFilterStore';
import { numberUtils } from '../utils/formatters';
import type { DashboardFilters, ExecutiveOverviewData, KPIMetric } from '../types';

interface DaySelection {
  id: number;
  date: string;
}

interface MetricRow {
  key: string;
  label: string;
  render: (data: ExecutiveOverviewData) => string;
}

const MAX_DAYS = 5;

const getBrowserTimeZone = (): string => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/Phoenix';
  } catch {
    return 'America/Phoenix';
  }
};

const deriveMissedCalls = (data: ExecutiveOverviewData): number => {
  const offered = data.offered?.value ?? 0;
  const abandonRate = data.abandonRate?.value ?? 0;
  return Math.max(0, Math.round(offered * (abandonRate / 100)));
};

const getMissedCallsDisplay = (data: ExecutiveOverviewData): string => {
  if (data.missedCalls) {
    return metricToDisplay(data.missedCalls);
  }
  return numberUtils.formatNumber(deriveMissedCalls(data));
};

const getMissedPercentDisplay = (data: ExecutiveOverviewData): string => {
  if (data.missedPercent) {
    return metricToDisplay(data.missedPercent);
  }
  return metricToDisplay(data.abandonRate);
};

const getVoicemailDisplay = (data: ExecutiveOverviewData): string => {
  if (data.voicemailCalls) {
    return metricToDisplay(data.voicemailCalls);
  }
  return '0';
};

const getVoicemailPercentDisplay = (data: ExecutiveOverviewData): string => {
  const offered = data.offered?.value ?? 0;
  const voicemailCalls = data.voicemailCalls?.value ?? 0;
  if (offered <= 0) {
    return '0.0%';
  }
  return `${((voicemailCalls / offered) * 100).toFixed(1)}%`;
};

const getAbandonedCountDisplay = (data: ExecutiveOverviewData): string => {
  if (data.missedCalls && data.voicemailCalls) {
    const abandoned = Math.max(0, data.missedCalls.value - data.voicemailCalls.value);
    return numberUtils.formatNumber(Math.round(abandoned));
  }

  if (data.missedCalls) {
    return metricToDisplay(data.missedCalls);
  }

  return numberUtils.formatNumber(deriveMissedCalls(data));
};

const metricRows: MetricRow[] = [
  { key: 'offered', label: 'Offered Calls', render: (data) => metricToDisplay(data.offered) },
  { key: 'abandoned_count', label: 'Abandoned', render: (data) => getAbandonedCountDisplay(data) },
  { key: 'abandoned_percent', label: 'Abandoned Percent', render: (data) => metricToDisplay(data.abandonRate) },
  { key: 'voicemail_calls', label: 'Voicemail Calls', render: (data) => getVoicemailDisplay(data) },
  { key: 'voicemail_percent', label: 'Voicemail Percent', render: (data) => getVoicemailPercentDisplay(data) },
  { key: 'missed_calls', label: 'Missed Calls', render: (data) => getMissedCallsDisplay(data) },
  { key: 'missed_percent', label: 'Missed Percent', render: (data) => getMissedPercentDisplay(data) },
  { key: 'answerRate', label: 'Answer Percent', render: (data) => metricToDisplay(data.answerRate) },
  { key: 'serviceLevel', label: 'Service Level Percent', render: (data) => metricToDisplay(data.serviceLevel) },
  { key: 'asa', label: 'ASA', render: (data) => metricToDisplay(data.asa) },
  { key: 'aht', label: 'AHT', render: (data) => metricToDisplay(data.aht) },
  { key: 'avgMos', label: 'Average MOS', render: (data) => metricToDisplay(data.avgMos) },
];

const toInputDate = (date: Date): string => {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

const getSuggestedDay = (existingDates: string[]): string => {
  for (let offset = 0; offset <= 365; offset += 1) {
    const candidate = toInputDate(subDays(new Date(), offset));
    if (!existingDates.includes(candidate)) {
      return candidate;
    }
  }
  return toInputDate(new Date());
};

const metricToDisplay = (metric: KPIMetric): string => {
  if (metric.formattedValue) {
    return metric.formattedValue;
  }

  const unit = (metric.unit || '').toLowerCase();
  if (unit.includes('percent') || unit.includes('%')) {
    return `${metric.value.toFixed(1)}%`;
  }

  if (unit.includes('sec')) {
    return numberUtils.formatSeconds(Math.round(metric.value));
  }

  return numberUtils.formatNumber(Math.round(metric.value));
};

const formatUtcOffsetLabel = (date: Date, timeZone: string): string => {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone,
      timeZoneName: 'shortOffset',
    }).formatToParts(date);
    const tzPart = parts.find((part) => part.type === 'timeZoneName')?.value;
    if (tzPart && tzPart.startsWith('GMT')) {
      const suffix = tzPart.replace('GMT', '');
      if (!suffix) {
        return 'UTC+00:00';
      }
      const normalized = /^[-+]\d{1,2}$/.test(suffix) ? `${suffix}:00` : suffix;
      return `UTC${normalized}`;
    }
  } catch {
    // Fall back to a generic UTC label below.
  }
  return 'UTC';
};

const getTimeZoneOffsetMs = (date: Date, timeZone: string): number => {
  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });

  const parts = formatter.formatToParts(date);
  const partMap: Record<string, string> = {};
  parts.forEach((part) => {
    if (part.type !== 'literal') {
      partMap[part.type] = part.value;
    }
  });

  const asUtc = Date.UTC(
    Number(partMap.year),
    Number(partMap.month) - 1,
    Number(partMap.day),
    Number(partMap.hour),
    Number(partMap.minute),
    Number(partMap.second)
  );

  return asUtc - date.getTime();
};

const buildTimeZoneDayBoundary = (
  inputDate: string,
  timeZone: string,
  hour: number,
  minute: number,
  second: number
): Date => {
  const [year, month, day] = inputDate.split('-').map(Number);
  const utcReference = new Date(Date.UTC(year, month - 1, day, hour, minute, second));
  const offsetMs = getTimeZoneOffsetMs(utcReference, timeZone);
  return new Date(utcReference.getTime() - offsetMs);
};

const toComparisonFilters = (
  baseFilters: DashboardFilters,
  selectedDate: string,
  timeZone: string
): DashboardFilters => ({
  ...baseFilters,
  dateRange: {
    preset: 'custom',
    startDate: buildTimeZoneDayBoundary(selectedDate, timeZone, 0, 0, 0),
    endDate: buildTimeZoneDayBoundary(selectedDate, timeZone, 23, 59, 59),
  },
});

export default function DayComparer() {
  const { filters, updateTimezone } = useFilterStore();
  const [selectedDays, setSelectedDays] = useState<DaySelection[]>([
    { id: 1, date: toInputDate(new Date()) },
  ]);
  const [dayData, setDayData] = useState<Record<string, ExecutiveOverviewData>>({});
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const sortedSelectedDays = useMemo(
    () => [...selectedDays].sort((a, b) => a.date.localeCompare(b.date)),
    [selectedDays]
  );

  const timezoneLabel = useMemo(
    () => `${filters.timezone} (${formatUtcOffsetLabel(new Date(), filters.timezone)})`,
    [filters.timezone]
  );

  const isUtcMode = filters.timezone === 'UTC';

  const loadComparison = useCallback(async () => {
    if (selectedDays.length === 0) {
      setDayData({});
      setError('Select at least one day to compare.');
      setLoading(false);
      return;
    }

    const dates = selectedDays.map((selection) => selection.date);
    const uniqueDates = new Set(dates);
    if (uniqueDates.size !== dates.length) {
      setError('Each selected day must be unique. Please remove duplicates.');
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const baseFilters: DashboardFilters = {
        ...filters,
        // This page compares day-level totals and does not need an agent scope.
        agentUuids: [],
      };

      const responseEntries = await Promise.all(
        selectedDays.map(async (selection) => {
          const timeZone = baseFilters.timezone || 'America/Phoenix';
          const response = await dashboardService.getExecutiveOverview(
            toComparisonFilters(baseFilters, selection.date, timeZone)
          );
          return [selection.date, response] as const;
        })
      );

      const nextDayData: Record<string, ExecutiveOverviewData> = {};
      responseEntries.forEach(([date, data]) => {
        nextDayData[date] = data;
      });

      setDayData(nextDayData);
    } catch (err: any) {
      setError(err?.message || 'Failed to load comparison data.');
      setDayData({});
    } finally {
      setLoading(false);
    }
  }, [filters, selectedDays]);

  useEffect(() => {
    loadComparison();
  }, [loadComparison]);

  const addDay = () => {
    setSelectedDays((prev) => {
      if (prev.length >= MAX_DAYS) {
        return prev;
      }

      const nextId = Math.max(...prev.map((day) => day.id)) + 1;
      const nextDate = getSuggestedDay(prev.map((day) => day.date));
      return [...prev, { id: nextId, date: nextDate }];
    });
  };

  const removeDay = (id: number) => {
    setSelectedDays((prev) => {
      if (prev.length <= 1) {
        return prev;
      }
      return prev.filter((day) => day.id !== id);
    });
  };

  const updateDay = (id: number, date: string) => {
    setSelectedDays((prev) => prev.map((day) => (day.id === id ? { ...day, date } : day)));
  };

  const renderMetricValue = (date: string, row: MetricRow): string => {
    const data = dayData[date];
    if (!data) {
      return loading ? 'Loading...' : '-';
    }

    return row.render(data);
  };

  return (
    <div className="overflow-auto p-6 space-y-6">
      <div className="flex flex-col gap-2">
        <h1 className="text-3xl font-bold text-gray-900">Day Comparer</h1>
        <p className="text-sm text-gray-600">
          Starts with today by default. Add up to 5 days (sequential or non-sequential) and compare KPI stats side by side.
        </p>
      </div>

      <div className="card flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-gray-700">Timezone Used for Comparison</p>
          <p className="text-xs uppercase tracking-wide text-gray-500">{timezoneLabel}</p>
        </div>
        <label className="inline-flex items-center gap-2 text-sm text-gray-700">
          <input
            type="checkbox"
            checked={isUtcMode}
            onChange={(event) => updateTimezone(event.target.checked ? 'UTC' : getBrowserTimeZone())}
          />
          Use UTC timezone
        </label>
      </div>

      <div className="card space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-gray-600">
            Selected Days: <span className="font-semibold text-gray-900">{selectedDays.length}</span> / {MAX_DAYS}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={addDay}
              disabled={selectedDays.length >= MAX_DAYS}
            >
              Add Day
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={loadComparison}
              disabled={loading}
            >
              {loading ? 'Comparing...' : 'Compare Days'}
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
          {selectedDays.map((selection) => (
            <div key={selection.id} className="rounded-md border border-gray-200 p-3 bg-gray-50">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">Day {selection.id}</span>
                <button
                  type="button"
                  className="text-xs text-red-600 hover:text-red-700 disabled:text-gray-300"
                  onClick={() => removeDay(selection.id)}
                  disabled={selectedDays.length <= 1}
                >
                  Remove
                </button>
              </div>
              <input
                type="date"
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
                value={selection.date}
                onChange={(event) => updateDay(selection.id, event.target.value)}
              />
            </div>
          ))}
        </div>
      </div>

      {error && <div className="card border-red-200 bg-red-50 text-red-700">{error}</div>}

      {!error && (
        <div className="card">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-lg font-semibold text-gray-900">KPI Side-by-Side Comparison</h2>
            <span className="text-xs text-gray-500">Dates are sorted left to right</span>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse">
              <thead>
                <tr>
                  <th className="sticky left-0 bg-white border-b border-gray-200 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500">
                    Metric
                  </th>
                  {sortedSelectedDays.map((selection) => (
                    <th
                      key={selection.id}
                      className="border-b border-gray-200 px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 whitespace-nowrap"
                    >
                      {selection.date}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metricRows.map((row) => (
                  <tr key={row.key} className="odd:bg-gray-50 even:bg-white">
                    <td className="sticky left-0 bg-inherit border-b border-gray-100 px-3 py-3 text-sm font-medium text-gray-800">
                      {row.label}
                    </td>
                    {sortedSelectedDays.map((selection) => (
                      <td
                        key={`${row.key}-${selection.id}`}
                        className="border-b border-gray-100 px-4 py-3 text-sm font-semibold text-gray-900 whitespace-nowrap"
                      >
                        {renderMetricValue(selection.date, row)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
