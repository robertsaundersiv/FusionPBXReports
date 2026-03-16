import { useState, useEffect } from 'react';
import { useFilterStore } from '../hooks/useFilterStore';
import DashboardFilterBar from '../components/DashboardFilterBar';
import KPICard from '../components/KPICard';
import { dashboardService } from '../services/dashboard';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { X } from 'lucide-react';
import type { ExecutiveOverviewData, Queue, Agent, KPIMetric } from '../types';

function formatHourBucketLabel(value: string) {
  const hour = Number.parseInt(value.slice(0, 2), 10);
  const suffix = hour >= 12 ? 'PM' : 'AM';
  const displayHour = hour % 12 === 0 ? 12 : hour % 12;
  return `${displayHour}${suffix[0]}`;
}

function formatDurationLabel(totalSeconds: number) {
  const normalizedSeconds = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(normalizedSeconds / 3600);
  const minutes = Math.floor((normalizedSeconds % 3600) / 60);
  const seconds = normalizedSeconds % 60;
  const parts = [];

  if (hours > 0) {
    parts.push(`${hours} hour${hours === 1 ? '' : 's'}`);
  }
  if (minutes > 0) {
    parts.push(`${minutes} minute${minutes === 1 ? '' : 's'}`);
  }
  if (seconds > 0 || parts.length === 0) {
    parts.push(`${seconds} second${seconds === 1 ? '' : 's'}`);
  }

  return parts.join(', ');
}

export default function ExecutiveOverview() {
  const { filters, updateDateRange, updateQueueIds, updateDirection } = useFilterStore();
  const [data, setData] = useState<ExecutiveOverviewData | null>(null);
  const [queues, setQueues] = useState<Queue[]>([]);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedDefinition, setSelectedDefinition] = useState<KPIMetric | null>(null);

  // Load metadata once on mount
  useEffect(() => {
    const loadMetadata = async () => {
      try {
        const [queuesData, agentsData] = await Promise.all([
          dashboardService.getQueues(),
          dashboardService.getAgents(),
        ]);
        console.log('📊 Loaded queues:', queuesData);
        console.log('📊 Loaded agents:', agentsData);
        setQueues(queuesData);
        setAgents(agentsData);
      } catch (err) {
        console.error('Error loading metadata:', err);
      }
    };
    loadMetadata();
  }, []);

  // Load dashboard data when filters change
  useEffect(() => {
    console.log('Filters changed, reloading data...', filters);
    setLoading(true);
    dashboardService.getExecutiveOverview(filters)
      .then((overviewData) => {
        console.log('Data loaded:', overviewData);
        setData(overviewData);
        setLoading(false);
      })
      .catch((error) => {
        console.error('Error loading dashboard data:', error);
        setLoading(false);
      });
  }, [filters]);

  if (loading) {
    return <div className="p-8 text-center">Loading Executive Overview...</div>;
  }

  if (!data) {
    return <div className="p-8 text-center text-red-600">Failed to load data</div>;
  }

  const weekdayBuckets = data.trends.callVolumeBuckets?.byDayOfWeek ?? [];
  const hourBuckets = data.trends.callVolumeBuckets?.byHourOfDay ?? [];
  const totalTalkTimeMetric: KPIMetric = {
    ...data.totalTalkTime,
    formattedValue: formatDurationLabel(data.totalTalkTime.value),
    unit: '',
  };

  return (
    <div className="overflow-auto">
      <DashboardFilterBar
        filters={filters}
        queues={queues}
        agents={agents.filter(
          (a): a is Agent & { agent_uuid?: string; agent_id?: string | number } =>
            Boolean(a.agent_uuid) || a.agent_id !== undefined
        )}
        onFiltersChange={(newFilters) => {
          updateDateRange(newFilters.dateRange);
          updateQueueIds(newFilters.queueIds);
          updateDirection(newFilters.direction);
          
        }}
      />

      <div className="p-6 space-y-6">
        {/* KPI Strip */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <KPICard metric={data.offered} onDefinitionClick={() => setSelectedDefinition(data.offered)} />
          <KPICard metric={data.answerRate} onDefinitionClick={() => setSelectedDefinition(data.answerRate)} />
          <KPICard metric={data.abandonRate} onDefinitionClick={() => setSelectedDefinition(data.abandonRate)} />
          <KPICard metric={data.serviceLevel} onDefinitionClick={() => setSelectedDefinition(data.serviceLevel)} />
          <KPICard metric={data.asa} onDefinitionClick={() => setSelectedDefinition(data.asa)} />
          <KPICard metric={data.aht} onDefinitionClick={() => setSelectedDefinition(data.aht)} />
          <KPICard metric={data.avgMos} onDefinitionClick={() => setSelectedDefinition(data.avgMos)} />
          <KPICard metric={totalTalkTimeMetric} onDefinitionClick={() => setSelectedDefinition(data.totalTalkTime)} />
        </div>

        {/* Trend Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Call Volume Trend */}
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">Daily Call Volume Trend</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={data.trends.offered}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="value" stroke="#0ea5e9" name="Offered" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* Service Level Trend */}
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">Answered Calls &lt; 30 Sec</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={data.trends.serviceLevel}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="value" stroke="#10b981" name="Service Level %" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* ASA Trend */}
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">Average Speed of Answer Trend</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={data.trends.asa}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="value" stroke="#f59e0b" name="ASA (sec)" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* AHT Trend */}
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">Average Handle Time Trend</h3>
            <ResponsiveContainer width="100%" height={300}>
              <LineChart data={data.trends.aht}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="date" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="value" stroke="#8b5cf6" name="AHT (sec)" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="card">
            <div className="mb-4">
              <h3 className="text-lg font-semibold">Call Volume by Weekday</h3>
              <p className="text-sm text-slate-500">The number under each weekday is how many times that day occurs in the selected range.</p>
            </div>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={weekdayBuckets} margin={{ top: 8, right: 16, left: 0, bottom: 24 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis
                  dataKey="bucket"
                  interval={0}
                  height={56}
                  tick={({ x = 0, y = 0, payload }) => {
                    const bucket = String(payload?.value ?? '');
                    // const matchingBucket = weekdayBuckets.find((item) => item.bucket === bucket);
                    // const occurrenceCount = matchingBucket?.occurrences ?? 0;

                    return (
                      <g transform={`translate(${x},${y})`}>
                        <text x={0} y={0} textAnchor="middle" fill="#475569" fontSize={12}>
                          <tspan x={0} dy="0.71em">{bucket}</tspan>
                          {/* <tspan x={0} dy="1.3em" fill="#94a3b8">{occurrenceCount}</tspan> */}
                        </text>
                      </g>
                    );
                  }}
                />
                <YAxis yAxisId="average" />
                <Tooltip
                  formatter={(value: number, name: string) => [
                    name === 'Average Calls' ? value.toFixed(2) : value,
                    name,
                  ]}
                  labelFormatter={(label) => `${label}`}
                />
                <Legend />
                <Line yAxisId="average" type="monotone" dataKey="averageCalls" stroke="#f59e0b" strokeWidth={3} name="Average Calls" />
              </LineChart>
            </ResponsiveContainer>
          </div>

          <div className="card">
            <div className="mb-4">
              <h3 className="text-lg font-semibold">Call Volume by Hour</h3>
              <p className="text-sm text-slate-500">Hourly buckets across the selected date range.</p>
            </div>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={hourBuckets} margin={{ top: 8, right: 16, left: 0, bottom: 16 }}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="bucket" tickFormatter={formatHourBucketLabel} height={40} interval={1} />
                <YAxis yAxisId="average" />
                <Tooltip
                  formatter={(value: number, name: string) => [
                    name === 'Average Calls' ? value.toFixed(2) : value,
                    name,
                  ]}
                  labelFormatter={(label) => `${formatHourBucketLabel(String(label))} bucket`}
                />
                <Legend />
                <Line yAxisId="average" type="monotone" dataKey="averageCalls" stroke="#dc2626" strokeWidth={3} name="Average Calls" dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Rankings */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">Busiest Queues</h3>
            <div className="space-y-2">
              {data.rankings.busiestQueues && data.rankings.busiestQueues.length > 0 ? (
                data.rankings.busiestQueues.map((queue, idx) => (
                  <div key={idx} className="flex justify-between items-center py-2 border-b">
                    <span>{queue.name}</span>
                    <span className="font-semibold">{queue.calls} calls</span>
                  </div>
                ))
              ) : (
                <p className="text-gray-500 text-sm">No data available</p>
              )}
            </div>
          </div>

          <div className="card">
            <h3 className="text-lg font-semibold mb-4">Worst Abandon Rate Queues</h3>
            <div className="space-y-2">
              {data.rankings.worstAbandonQueues && data.rankings.worstAbandonQueues.length > 0 ? (
                data.rankings.worstAbandonQueues.map((queue, idx) => (
                  <div key={idx} className="flex justify-between items-center py-2 border-b">
                    <span>{queue.name}</span>
                    <span className="font-semibold text-red-600">{(queue.rate || 0).toFixed(1)}%</span>
                  </div>
                ))
              ) : (
                <p className="text-gray-500 text-sm">No data available</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* KPI Definition Modal */}
      {selectedDefinition && (
        <div 
          className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
          onClick={() => setSelectedDefinition(null)}
        >
          <div 
            className="bg-white rounded-lg shadow-xl p-6 max-w-lg w-full mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-between items-start mb-4">
              <h3 className="text-xl font-semibold text-gray-900">{selectedDefinition.name}</h3>
              <button
                onClick={() => setSelectedDefinition(null)}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X size={24} />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <p className="text-sm font-medium text-gray-700 mb-1">Definition</p>
                <p className="text-gray-600">{selectedDefinition.definition || 'No definition available.'}</p>
              </div>
              <div className="grid grid-cols-2 gap-4 pt-4 border-t">
                <div>
                  <p className="text-sm font-medium text-gray-700 mb-1">Current Value</p>
                  <p className="text-2xl font-bold text-gray-900">
                    {selectedDefinition.value.toFixed(selectedDefinition.unit === '%' ? 1 : 0)}{' '}
                    <span className="text-base text-gray-500">{selectedDefinition.unit}</span>
                  </p>
                </div>
                {selectedDefinition.threshold && (
                  <div>
                    <p className="text-sm font-medium text-gray-700 mb-1">Target</p>
                    <p className="text-sm text-gray-600">
                      Good: ≥ {selectedDefinition.threshold.good}{selectedDefinition.unit}
                      <br />
                      Warning: ≥ {selectedDefinition.threshold.warning}{selectedDefinition.unit}
                    </p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
