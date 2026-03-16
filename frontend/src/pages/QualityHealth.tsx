import { useEffect, useState } from 'react';
import { adminService } from '../services/admin';
import type { QualityHealthData } from '../types';

function formatTimestamp(value: string | null) {
  if (!value) {
    return 'Unavailable';
  }

  return new Date(value).toLocaleString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    second: '2-digit',
  });
}

export default function QualityHealth() {
  const [data, setData] = useState<QualityHealthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminService.getQualityHealth()
      .then((response) => {
        setData(response);
        setLoading(false);
      })
      .catch((requestError: any) => {
        setError(requestError.response?.data?.detail || 'Failed to load quality and task health data.');
        setLoading(false);
      });
  }, []);

  if (loading) {
    return <div className="p-8 text-center">Loading Quality & Health...</div>;
  }

  if (error || !data) {
    return <div className="p-8 text-center text-red-600">{error || 'Failed to load data.'}</div>;
  }

  return (
    <div className="p-6 space-y-6">
      <div>
        <h1 className="text-3xl font-bold text-gray-900">Quality & Health</h1>
        <p className="mt-2 text-sm text-gray-600">Super admin operational visibility for ETL state and Celery task execution.</p>
      </div>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-200">
          <p className="text-sm text-gray-500">Pipeline Status</p>
          <p className="mt-2 text-2xl font-semibold text-gray-900 uppercase">{data.pipeline_status.status}</p>
        </div>
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-200">
          <p className="text-sm text-gray-500">Last Successful Ingest</p>
          <p className="mt-2 text-sm font-medium text-gray-900">{formatTimestamp(data.pipeline_status.last_successful_run)}</p>
        </div>
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-200">
          <p className="text-sm text-gray-500">Last Queue Sync</p>
          <p className="mt-2 text-sm font-medium text-gray-900">{formatTimestamp(data.pipeline_status.last_queue_sync)}</p>
        </div>
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-200">
          <p className="text-sm text-gray-500">Last Agent Sync</p>
          <p className="mt-2 text-sm font-medium text-gray-900">{formatTimestamp(data.pipeline_status.last_agent_sync)}</p>
        </div>
      </section>

      <section className="rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-gray-900">Celery Tasks</h2>
            <p className="mt-1 text-sm text-gray-600">Last observed execution time for each active scheduled task.</p>
          </div>
          <div className="text-sm text-gray-500">Errors: {data.pipeline_status.error_count}</div>
        </div>

        {data.pipeline_status.error_message ? (
          <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {data.pipeline_status.error_message}
          </div>
        ) : null}

        <div className="mt-6 overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200 text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-gray-500">
                <th className="pb-3 pr-4">Task</th>
                <th className="pb-3 pr-4">Schedule</th>
                <th className="pb-3 pr-4">Last Executed</th>
                <th className="pb-3 pr-4">Source</th>
                <th className="pb-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {data.tasks.map((task) => (
                <tr key={task.task_name}>
                  <td className="py-4 pr-4">
                    <div className="font-medium text-gray-900">{task.display_name}</div>
                    <div className="text-xs text-gray-500">{task.task_name}</div>
                  </td>
                  <td className="py-4 pr-4 text-gray-700">{task.schedule}</td>
                  <td className="py-4 pr-4 text-gray-700">{formatTimestamp(task.last_executed_at)}</td>
                  <td className="py-4 pr-4 text-gray-700">{task.source}</td>
                  <td className="py-4 text-gray-700 uppercase">{task.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
