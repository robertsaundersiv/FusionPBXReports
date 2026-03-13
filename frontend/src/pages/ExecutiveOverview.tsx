import { useState, useEffect } from 'react';
import { useFilterStore } from '../hooks/useFilterStore';
import DashboardFilterBar from '../components/DashboardFilterBar';
import KPICard from '../components/KPICard';
import { dashboardService } from '../services/dashboard';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { X } from 'lucide-react';
import type { ExecutiveOverviewData, Queue, Agent, KPIMetric } from '../types';

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
          <KPICard metric={data.totalTalkTime} onDefinitionClick={() => setSelectedDefinition(data.totalTalkTime)} />
        </div>

        {/* Trend Charts */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Call Volume Trend */}
          <div className="card">
            <h3 className="text-lg font-semibold mb-4">Call Volume Trend</h3>
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
