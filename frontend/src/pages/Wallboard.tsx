import { useEffect, useMemo, useState } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';
import { useFilterStore } from '../hooks/useFilterStore';
import { dashboardService } from '../services/dashboard';
import type { WallboardLiveAgent, WallboardLiveQueue, WallboardLiveResponse } from '../types';
import { formatCount, formatSecondsToTime } from '../utils/queuePerformance';

const REFRESH_INTERVAL_MS = 5000;

function formatWallboardDateTime(date: Date, timeZone: string) {
  try {
    return new Intl.DateTimeFormat('en-US', {
      timeZone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    }).format(date);
  } catch {
    return date.toLocaleString();
  }
}

function agentTone(agent: WallboardLiveAgent): string {
  const state = (agent.state || '').toLowerCase();
  if (state.includes('answered') || state.includes('call')) {
    return 'border-emerald-600/40 bg-emerald-500/15 text-emerald-200';
  }
  if (state.includes('trying') || state.includes('ring')) {
    return 'border-amber-500/40 bg-amber-500/15 text-amber-200';
  }
  if (state.includes('wait') || state.includes('idle') || state.includes('ready')) {
    return 'border-sky-500/40 bg-sky-500/15 text-sky-200';
  }
  return 'border-slate-500/40 bg-slate-500/15 text-slate-200';
}

function queueBorder(queue: WallboardLiveQueue): string {
  if (queue.trying > 0) {
    return 'border-amber-500/60';
  }
  if (queue.abandoned > queue.answered && queue.abandoned > 0) {
    return 'border-rose-500/60';
  }
  return 'border-slate-600/80';
}

export default function Wallboard() {
  const configuredTimeZone = useFilterStore((state) => state.filters.timezone);
  const [data, setData] = useState<WallboardLiveResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [currentTime, setCurrentTime] = useState(new Date());

  const effectiveTimeZone = data?.timezone || configuredTimeZone || 'America/Phoenix';

  useEffect(() => {
    const timer = window.setInterval(() => setCurrentTime(new Date()), 1000);
    return () => window.clearInterval(timer);
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
        const response = await dashboardService.getWallboardLive(configuredTimeZone);
        if (!active) {
          return;
        }
        setData(response);
        setError(null);
      } catch (requestError: any) {
        if (!active) {
          return;
        }
        setError(requestError?.message || 'Failed to load live wallboard data');
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
  }, [configuredTimeZone]);

  const queues = data?.queues || [];
  const agents = data?.agents || [];

  const sortedQueues = useMemo(
    () => [...queues].sort((a, b) => b.trying - a.trying || b.answered - a.answered || a.queue_name.localeCompare(b.queue_name)),
    [queues]
  );

  const summary = data?.summary || {
    queue_count: queues.length,
    agent_count: agents.length,
    answered: queues.reduce((sum, item) => sum + item.answered, 0),
    trying: queues.reduce((sum, item) => sum + item.trying, 0),
    abandoned: queues.reduce((sum, item) => sum + item.abandoned, 0),
    total_talk_time_seconds: queues.reduce((sum, item) => sum + (item.talk_time_seconds || 0), 0),
    total_wait_time_seconds: queues.reduce((sum, item) => sum + (item.wait_time_seconds || 0), 0),
    average_talk_time_seconds: 0,
    average_wait_time_seconds: 0,
  };

  if (loading) {
    return (
      <div className="min-h-full bg-[#0a0f14] p-6 text-slate-100">
        <div className="mx-auto max-w-5xl rounded-2xl border border-slate-700 bg-slate-900/70 p-10 text-center">
          <RefreshCw className="mx-auto animate-spin text-sky-300" size={28} />
          <p className="mt-4 text-xl font-semibold">Loading wallboard</p>
          <p className="mt-2 text-sm text-slate-400">Waiting for queue and agent live data.</p>
        </div>
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="min-h-full bg-[#0a0f14] p-6 text-slate-100">
        <div className="mx-auto max-w-5xl rounded-2xl border border-rose-500/50 bg-rose-500/10 p-10 text-center">
          <AlertCircle className="mx-auto text-rose-300" size={28} />
          <p className="mt-4 text-xl font-semibold">Unable to load wallboard</p>
          <p className="mt-2 text-sm text-rose-200">{error}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-full bg-[radial-gradient(circle_at_top,#122130_0%,#0a0f14_55%)] text-slate-100">
      <div className="space-y-5 p-4 sm:p-6">
        <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-4 shadow-2xl shadow-black/40 sm:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-sky-300">Call Center Wallboard</p>
              <h1 className="mt-2 text-3xl font-semibold sm:text-4xl">Wi-Fiber Queue Monitor</h1>
              <p className="mt-2 text-sm text-slate-400">Live queue and agent snapshot from FusionPBX via PhoneReports API.</p>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <div className="rounded-xl border border-slate-700 bg-slate-950/60 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Date and Time</p>
                <p className="mt-2 text-lg font-semibold text-white">{formatWallboardDateTime(currentTime, effectiveTimeZone)}</p>
                <p className="mt-1 text-xs text-slate-500">{effectiveTimeZone}</p>
              </div>
              <div className="rounded-xl border border-slate-700 bg-slate-950/60 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Average Talk Time</p>
                <p className="mt-2 text-lg font-semibold text-white">{formatSecondsToTime(summary.average_talk_time_seconds)}</p>
                <p className="mt-1 text-xs text-slate-500">{formatSecondsToTime(summary.total_talk_time_seconds)} total</p>
              </div>
              <div className="rounded-xl border border-slate-700 bg-slate-950/60 px-4 py-3">
                <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Average Wait Time</p>
                <p className="mt-2 text-lg font-semibold text-white">{formatSecondsToTime(summary.average_wait_time_seconds)}</p>
                <p className="mt-1 text-xs text-slate-500">{formatSecondsToTime(summary.total_wait_time_seconds)} total</p>
              </div>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
            <span className="rounded-full border border-slate-600 bg-slate-900 px-3 py-1">{formatCount(summary.queue_count)} Queues</span>
            <span className="rounded-full border border-emerald-500/50 bg-emerald-500/10 px-3 py-1">{formatCount(summary.answered)} Answered</span>
            <span className="rounded-full border border-amber-500/50 bg-amber-500/10 px-3 py-1">{formatCount(summary.trying)} Trying</span>
            <span className="rounded-full border border-rose-500/50 bg-rose-500/10 px-3 py-1">{formatCount(summary.abandoned)} Abandoned</span>
            <button
              type="button"
              onClick={() => {
                setRefreshing(true);
                void dashboardService
                  .getWallboardLive(effectiveTimeZone)
                  .then((response) => {
                    setData(response);
                    setError(null);
                  })
                  .catch((requestError: any) => {
                    setError(requestError?.message || 'Failed to refresh wallboard data');
                  })
                  .finally(() => {
                    setRefreshing(false);
                  });
              }}
              className="ml-auto inline-flex items-center gap-2 rounded-lg border border-slate-500 bg-slate-800 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.2em] text-slate-100 hover:bg-slate-700"
            >
              <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
              Refresh
            </button>
          </div>

          {error ? (
            <p className="mt-3 text-sm text-amber-300">{error}. Showing the last successful snapshot.</p>
          ) : null}
        </section>

        <section>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {sortedQueues.map((queue) => (
              <article
                key={queue.queue_id}
                className={`rounded-xl border bg-slate-900/80 p-4 shadow-lg shadow-black/30 ${queueBorder(queue)}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.2em] text-slate-500">{queue.queue_extension || 'Queue'}</p>
                    <p className="mt-1 text-sm font-semibold text-white">{queue.queue_name}</p>
                  </div>
                  <p className="text-4xl font-bold leading-none text-amber-300">{formatCount(queue.trying)}</p>
                </div>

                <div className="mt-3 grid grid-cols-3 gap-2 text-center text-xs">
                  <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 px-2 py-2">
                    <p className="uppercase tracking-[0.18em] text-emerald-200">Answered</p>
                    <p className="mt-1 text-base font-semibold text-white">{formatCount(queue.answered)}</p>
                  </div>
                  <div className="rounded-md border border-amber-500/40 bg-amber-500/10 px-2 py-2">
                    <p className="uppercase tracking-[0.18em] text-amber-200">Trying</p>
                    <p className="mt-1 text-base font-semibold text-white">{formatCount(queue.trying)}</p>
                  </div>
                  <div className="rounded-md border border-rose-500/40 bg-rose-500/10 px-2 py-2">
                    <p className="uppercase tracking-[0.18em] text-rose-200">Abandoned</p>
                    <p className="mt-1 text-base font-semibold text-white">{formatCount(queue.abandoned)}</p>
                  </div>
                </div>
              </article>
            ))}
          </div>

          {sortedQueues.length === 0 ? (
            <div className="mt-4 rounded-xl border border-dashed border-slate-600 bg-slate-900/60 p-8 text-center text-slate-400">
              No live queue records returned yet.
            </div>
          ) : null}
        </section>

        <section className="rounded-2xl border border-slate-700 bg-slate-900/70 p-4 shadow-2xl shadow-black/40 sm:p-5">
          <h2 className="text-lg font-semibold text-white">Agent Status</h2>
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
            {agents.map((agent) => (
              <div key={agent.agent_id || agent.agent_name} className={`rounded-lg border px-3 py-3 ${agentTone(agent)}`}>
                <p className="text-xs uppercase tracking-[0.2em]">{agent.state}</p>
                <p className="mt-1 truncate text-sm font-semibold text-white">{agent.agent_name}</p>
                <p className="mt-1 text-xs text-slate-300">{formatCount(agent.answered)} answered</p>
                <p className="mt-1 text-xs text-slate-400">
                  {agent.last_change_seconds != null
                    ? `${formatSecondsToTime(agent.last_change_seconds)} last change`
                    : 'Last change unavailable'}
                </p>
              </div>
            ))}
          </div>

          {agents.length === 0 ? (
            <p className="mt-3 text-sm text-slate-400">No live agent statuses returned yet.</p>
          ) : null}
        </section>
      </div>
    </div>
  );
}