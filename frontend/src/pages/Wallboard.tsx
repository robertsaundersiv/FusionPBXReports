import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, Clock3, RefreshCw } from 'lucide-react';
import { useFilterStore } from '../hooks/useFilterStore';
import { dashboardService } from '../services/dashboard';
import type { DashboardFilters, QueuePerformanceHourlyData } from '../types';
import {
  formatCount,
  formatMOS,
  formatPercentage,
  formatSecondsToTime,
  formatHourlyTimestamp,
} from '../utils/queuePerformance';

const REFRESH_INTERVAL_MS = 30000;
const WALLBOARD_WINDOW_HOURS = 24;

function formatWallboardDateTime(date: Date, timeZone: string) {
  try {
    return new Intl.DateTimeFormat('en-US', {
      timeZone,
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    }).format(date);
  } catch {
    return date.toLocaleString();
  }
}

function formatWallboardWindow(date: Date, timeZone: string) {
  try {
    return new Intl.DateTimeFormat('en-US', {
      timeZone,
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    }).format(date);
  } catch {
    return date.toLocaleString();
  }
}

function buildWallboardFilters(timeZone: string): DashboardFilters {
  const endDate = new Date();
  const startDate = new Date(endDate.getTime() - WALLBOARD_WINDOW_HOURS * 60 * 60 * 1000);

  return {
    dateRange: {
      preset: 'custom',
      startDate,
      endDate,
    },
    queueIds: [],
    agentUuids: [],
    direction: 'inbound',
    businessHoursOnly: false,
    includeOutbound: false,
    excludeDeflects: true,
    strictQueueAnswered: false,
    timezone: timeZone,
  };
}

function getQueueStatus(queue: QueuePerformanceHourlyData) {
  const offered = queue.metrics.offered.value;
  const answerRate = queue.metrics.answer_rate.value;
  const serviceLevel = queue.metrics.service_level.value;
  const abandonRate = queue.metrics.abandon_rate.value;

  if (offered === 0) {
    return {
      label: 'Quiet',
      className: 'border-slate-200 bg-slate-50 text-slate-600',
    };
  }

  if (serviceLevel >= 80 && answerRate >= 90 && abandonRate <= 5) {
    return {
      label: 'Healthy',
      className: 'border-emerald-200 bg-emerald-50 text-emerald-700',
    };
  }

  if (serviceLevel >= 65 && abandonRate <= 10) {
    return {
      label: 'Watch',
      className: 'border-amber-200 bg-amber-50 text-amber-700',
    };
  }

  return {
    label: 'Alert',
    className: 'border-rose-200 bg-rose-50 text-rose-700',
  };
}

function QueueTrendStrip({ hourly }: { hourly: QueuePerformanceHourlyData['hourly'] }) {
  const recentHourly = hourly.slice(-12);
  const peakOffered = recentHourly.reduce((max, point) => Math.max(max, point.offered), 0);

  if (recentHourly.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 px-4 py-6 text-center text-sm text-slate-500">
        No hourly data available yet.
      </div>
    );
  }

  return (
    <div className="rounded-2xl bg-slate-50 p-3">
      <div className="mb-2 flex items-center justify-between text-xs text-slate-500">
        <span>Hourly offered trend</span>
        <span>{recentHourly.length} points</span>
      </div>
      <div className="flex h-16 items-end gap-1">
        {recentHourly.map((point) => {
          const height = peakOffered > 0 ? Math.max(8, Math.round((point.offered / peakOffered) * 100)) : 8;

          return (
            <div
              key={point.timestamp}
              title={`${formatHourlyTimestamp(point.timestamp, false)} • ${formatCount(point.offered)} offered`}
              className="flex-1 rounded-t-md bg-gradient-to-t from-blue-600 via-sky-500 to-cyan-300"
              style={{ height: `${height}%` }}
            />
          );
        })}
      </div>
    </div>
  );
}

export default function Wallboard() {
  const timeZone = useFilterStore((state) => state.filters.timezone);
  const [queueData, setQueueData] = useState<QueuePerformanceHourlyData[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => {
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let active = true;

    const loadWallboard = async (showLoadingState: boolean) => {
      if (showLoadingState) {
        setLoading(true);
      } else {
        setRefreshing(true);
      }

      try {
        const response = await dashboardService.getQueuePerformance(buildWallboardFilters(timeZone));

        if (!active) {
          return;
        }

        setQueueData(response.queues ?? []);
        setLastUpdated(new Date());
        setError(null);
      } catch (requestError: any) {
        if (!active) {
          return;
        }

        setError(requestError?.message || 'Failed to load wallboard data');
      } finally {
        if (!active) {
          return;
        }

        if (showLoadingState) {
          setLoading(false);
        } else {
          setRefreshing(false);
        }
      }
    };

    void loadWallboard(true);
    const intervalId = window.setInterval(() => {
      void loadWallboard(false);
    }, REFRESH_INTERVAL_MS);

    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, [timeZone]);

  const summary = useMemo(() => {
    const initial = {
      queueCount: queueData.length,
      activeQueueCount: 0,
      offered: 0,
      answered: 0,
      abandoned: 0,
      weightedServiceLevel: 0,
      weightedAsa: 0,
      weightedAht: 0,
      weightedMos: 0,
      answeredWeight: 0,
    };

    for (const queue of queueData) {
      const offered = queue.metrics.offered.value;
      const answered = queue.metrics.answered.value;

      if (offered > 0) {
        initial.activeQueueCount += 1;
      }

      initial.offered += offered;
      initial.answered += answered;
      initial.abandoned += queue.metrics.abandoned.value;
      initial.weightedServiceLevel += queue.metrics.service_level.value * answered;
      initial.weightedAsa += queue.metrics.asa_avg.value * answered;
      initial.weightedAht += queue.metrics.aht_avg.value * answered;
      initial.weightedMos += queue.metrics.mos_avg.value * answered;
      initial.answeredWeight += answered;
    }

    return {
      queueCount: initial.queueCount,
      activeQueueCount: initial.activeQueueCount,
      offered: initial.offered,
      answered: initial.answered,
      abandoned: initial.abandoned,
      answerRate: initial.offered > 0 ? (initial.answered / initial.offered) * 100 : 0,
      serviceLevel: initial.answeredWeight > 0 ? initial.weightedServiceLevel / initial.answeredWeight : null,
      asa: initial.answeredWeight > 0 ? initial.weightedAsa / initial.answeredWeight : null,
      aht: initial.answeredWeight > 0 ? initial.weightedAht / initial.answeredWeight : null,
      mos: initial.answeredWeight > 0 ? initial.weightedMos / initial.answeredWeight : null,
    };
  }, [queueData]);

  const sortedQueues = useMemo(
    () => [...queueData].sort((a, b) => b.metrics.offered.value - a.metrics.offered.value),
    [queueData]
  );

  const summaryCards = [
    {
      label: 'Queues',
      value: formatCount(summary.queueCount),
      hint: `${formatCount(summary.activeQueueCount)} active`,
      tone: 'blue',
    },
    {
      label: 'Offered',
      value: formatCount(summary.offered),
      hint: 'Rolling 24h',
      tone: 'sky',
    },
    {
      label: 'Answered',
      value: formatCount(summary.answered),
      hint: `${formatPercentage(summary.answerRate)} answer rate`,
      tone: 'emerald',
    },
    {
      label: 'Abandoned',
      value: formatCount(summary.abandoned),
      hint: 'Rolling 24h',
      tone: 'rose',
    },
    {
      label: 'Service Level',
      value: formatPercentage(summary.serviceLevel),
      hint: '30-second target',
      tone: 'violet',
    },
    {
      label: 'ASA',
      value: formatSecondsToTime(summary.asa),
      hint: 'Average speed of answer',
      tone: 'amber',
    },
    {
      label: 'AHT',
      value: formatSecondsToTime(summary.aht),
      hint: 'Answered calls only',
      tone: 'cyan',
    },
    {
      label: 'MOS',
      value: formatMOS(summary.mos),
      hint: 'Voice quality',
      tone: 'pink',
    },
  ] as const;

  const toneStyles: Record<(typeof summaryCards)[number]['tone'], string> = {
    blue: 'border-blue-100 bg-blue-50 text-blue-700',
    sky: 'border-sky-100 bg-sky-50 text-sky-700',
    emerald: 'border-emerald-100 bg-emerald-50 text-emerald-700',
    rose: 'border-rose-100 bg-rose-50 text-rose-700',
    violet: 'border-violet-100 bg-violet-50 text-violet-700',
    amber: 'border-amber-100 bg-amber-50 text-amber-700',
    cyan: 'border-cyan-100 bg-cyan-50 text-cyan-700',
    pink: 'border-pink-100 bg-pink-50 text-pink-700',
  };

  if (loading) {
    return (
      <div className="min-h-full bg-slate-50 p-6">
        <div className="rounded-3xl border border-slate-200 bg-white p-10 text-center shadow-sm">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-blue-600">
            <RefreshCw className="animate-spin" size={20} />
          </div>
          <p className="mt-4 text-lg font-semibold text-slate-900">Loading wallboard snapshot</p>
          <p className="mt-2 text-sm text-slate-500">Pulling the latest 24-hour queue data.</p>
        </div>
      </div>
    );
  }

  if (error && queueData.length === 0) {
    return (
      <div className="min-h-full bg-slate-50 p-6">
        <div className="rounded-3xl border border-red-200 bg-white p-10 text-center shadow-sm">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-red-50 text-red-600">
            <AlertCircle size={20} />
          </div>
          <p className="mt-4 text-lg font-semibold text-slate-900">Unable to load wallboard data</p>
          <p className="mt-2 text-sm text-red-700">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-full bg-slate-50">
      <div className="p-6 space-y-6">
        <section className="rounded-3xl border border-slate-200 bg-gradient-to-br from-slate-950 via-slate-900 to-blue-900 p-6 text-white shadow-xl">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-blue-100">
                <span className="h-2 w-2 rounded-full bg-emerald-400" />
                Live wallboard
              </div>
              <h1 className="mt-4 text-4xl font-bold tracking-tight">Wallboard</h1>
              <p className="mt-2 max-w-3xl text-sm text-slate-300">
                Rolling 24-hour queue view built from the same call-centre metrics as the rest of the project, optimized for quick monitoring.
              </p>
              <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-200">
                <span className="rounded-full bg-white/10 px-3 py-1">Inbound only</span>
                <span className="rounded-full bg-white/10 px-3 py-1">Auto refresh every 30s</span>
                <span className="rounded-full bg-white/10 px-3 py-1">{formatCount(summary.queueCount)} queues</span>
              </div>
            </div>

            <div className="grid gap-3 sm:grid-cols-2 lg:min-w-[28rem]">
              <div className="rounded-2xl bg-white/10 p-4 backdrop-blur-sm">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-slate-300">
                  <Clock3 size={14} />
                  Current time
                </div>
                <p className="mt-3 text-xl font-semibold text-white">{formatWallboardDateTime(currentTime, timeZone)}</p>
                <p className="mt-1 text-xs text-slate-400">{timeZone}</p>
              </div>
              <div className="rounded-2xl bg-white/10 p-4 backdrop-blur-sm">
                <div className="flex items-center gap-2 text-xs uppercase tracking-[0.2em] text-slate-300">
                  <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
                  Last refresh
                </div>
                <p className="mt-3 text-xl font-semibold text-white">
                  {lastUpdated ? formatWallboardDateTime(lastUpdated, timeZone) : 'Waiting for data'}
                </p>
                <p className="mt-1 text-xs text-slate-400">Rolling window: {formatWallboardWindow(new Date(Date.now() - WALLBOARD_WINDOW_HOURS * 60 * 60 * 1000), timeZone)} - now</p>
              </div>
            </div>
          </div>
        </section>

        {error && queueData.length > 0 ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            Latest refresh failed: {error}. Showing the last successful snapshot.
          </div>
        ) : null}

        <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {summaryCards.map((card) => (
            <div key={card.label} className={`rounded-2xl border p-4 shadow-sm ${toneStyles[card.tone]}`}>
              <p className="text-xs font-semibold uppercase tracking-[0.2em] opacity-80">{card.label}</p>
              <p className="mt-2 text-3xl font-bold text-slate-900">{card.value}</p>
              <p className="mt-1 text-sm text-slate-600">{card.hint}</p>
            </div>
          ))}
        </section>

        <section className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <h2 className="text-2xl font-bold text-slate-900">Queue snapshot</h2>
              <p className="text-sm text-slate-500">Queues are sorted by offered volume so the busiest lines stay at the top.</p>
            </div>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setRefreshing(true);
                void (async () => {
                  try {
                    const response = await dashboardService.getQueuePerformance(buildWallboardFilters(timeZone));
                    setQueueData(response.queues ?? []);
                    setLastUpdated(new Date());
                  } catch (requestError: any) {
                    setError(requestError?.message || 'Failed to load wallboard data');
                  } finally {
                    setRefreshing(false);
                  }
                })();
              }}
              className="inline-flex items-center gap-2 rounded-xl bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800"
            >
              <RefreshCw size={16} className={refreshing ? 'animate-spin' : ''} />
              Refresh now
            </button>
          </div>

          {sortedQueues.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-8 text-center text-slate-500 shadow-sm">
              No queue data is available for the current window.
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {sortedQueues.map((queue) => {
                const status = getQueueStatus(queue);

                return (
                  <article key={queue.queue_id} className="rounded-3xl border border-slate-200 bg-white p-5 shadow-sm transition-shadow hover:shadow-md">
                    <div className="flex items-start justify-between gap-4">
                      <div>
                        <h3 className="text-lg font-semibold text-slate-900">{queue.queue_name}</h3>
                        <p className="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">Rolling 24-hour snapshot</p>
                      </div>
                      <span className={`inline-flex items-center rounded-full border px-3 py-1 text-xs font-semibold ${status.className}`}>
                        {status.label}
                      </span>
                    </div>

                    <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
                      <div className="rounded-2xl bg-blue-50 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-blue-700">Offered</p>
                        <p className="mt-1 text-xl font-semibold text-slate-900">{formatCount(queue.metrics.offered.value)}</p>
                      </div>
                      <div className="rounded-2xl bg-emerald-50 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">Answered</p>
                        <p className="mt-1 text-xl font-semibold text-slate-900">{formatCount(queue.metrics.answered.value)}</p>
                      </div>
                      <div className="rounded-2xl bg-rose-50 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-700">Abandoned</p>
                        <p className="mt-1 text-xl font-semibold text-slate-900">{formatCount(queue.metrics.abandoned.value)}</p>
                      </div>
                      <div className="rounded-2xl bg-violet-50 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-violet-700">Service Level</p>
                        <p className="mt-1 text-xl font-semibold text-slate-900">{formatPercentage(queue.metrics.service_level.value)}</p>
                      </div>
                      <div className="rounded-2xl bg-amber-50 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-700">ASA</p>
                        <p className="mt-1 text-xl font-semibold text-slate-900">{formatSecondsToTime(queue.metrics.asa_avg.value)}</p>
                      </div>
                      <div className="rounded-2xl bg-cyan-50 p-3">
                        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-cyan-700">AHT</p>
                        <p className="mt-1 text-xl font-semibold text-slate-900">{formatSecondsToTime(queue.metrics.aht_avg.value)}</p>
                      </div>
                    </div>

                    <div className="mt-4 flex flex-wrap gap-2 text-xs text-slate-600">
                      <span className="rounded-full bg-slate-100 px-3 py-1">Answer rate {formatPercentage(queue.metrics.answer_rate.value)}</span>
                      <span className="rounded-full bg-slate-100 px-3 py-1">MOS {formatMOS(queue.metrics.mos_avg.value)}</span>
                      <span className="rounded-full bg-slate-100 px-3 py-1">Abandon rate {formatPercentage(queue.metrics.abandon_rate.value)}</span>
                    </div>

                    <div className="mt-5">
                      <QueueTrendStrip hourly={queue.hourly} />
                    </div>
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}