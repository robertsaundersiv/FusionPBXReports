import { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import {
  formatCount,
  formatPercentage,
  formatSecondsToTime,
  formatMOS,
  formatHourlyTimestamp,
} from '../utils/queuePerformance';
import type { QueuePerformanceHourlyData } from '../types';

interface QueuePerformanceCardProps {
  queueData: QueuePerformanceHourlyData;
  groupPrefix?: string;
}

type ChartMetric = 'offered' | 'answered' | 'abandoned' | 'service_level' | 'asa' | 'aht' | 'mos';

export default function QueuePerformanceCard({ queueData, groupPrefix }: QueuePerformanceCardProps) {
  const [selectedMetric, setSelectedMetric] = useState<ChartMetric>('offered');

  const { queue_name, metrics, hourly } = queueData;

  // Prepare chart data based on selected metric
  const chartData = hourly.map((h) => ({
    timestamp: h.timestamp,
    displayTime: formatHourlyTimestamp(h.timestamp, hourly.length > 48), // Show date if >2 days
    value: h[selectedMetric],
  }));

  // Get metric label and color
  const metricConfig: Record<ChartMetric, { label: string; color: string; unit: string }> = {
    offered: { label: 'Offered', color: '#0ea5e9', unit: 'calls' },
    answered: { label: 'Answered', color: '#10b981', unit: 'calls' },
    abandoned: { label: 'Abandoned (No VM)', color: '#ef4444', unit: 'calls' },
    service_level: { label: 'Service Level %', color: '#8b5cf6', unit: '%' },
    asa: { label: 'ASA', color: '#f59e0b', unit: 'sec' },
    aht: { label: 'AHT', color: '#06b6d4', unit: 'sec' },
    mos: { label: 'MOS', color: '#ec4899', unit: '' },
  };

  const currentConfig = metricConfig[selectedMetric];

  // Custom tooltip formatter
  const customTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      const data = payload[0].payload;
      let formattedValue = data.value;

      if (data.value === null || data.value === undefined) {
        formattedValue = 'N/A';
      } else if (selectedMetric === 'service_level') {
        formattedValue = formatPercentage(data.value);
      } else if (selectedMetric === 'asa' || selectedMetric === 'aht') {
        formattedValue = formatSecondsToTime(data.value);
      } else if (selectedMetric === 'mos') {
        formattedValue = formatMOS(data.value);
      } else {
        formattedValue = formatCount(data.value);
      }

      return (
        <div className="bg-white p-3 border border-gray-300 rounded shadow-lg">
          <p className="text-sm font-medium text-gray-900">{data.displayTime}</p>
          <p className="text-sm text-gray-600">
            {currentConfig.label}: <span className="font-semibold">{formattedValue}</span>
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className="card">
      {/* Card Header */}
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-gray-200">
        <div>
          <h3 className="text-lg font-bold text-gray-900">{queue_name}</h3>
          {groupPrefix && (
            <span className="inline-block mt-1 px-2 py-0.5 text-xs font-medium bg-blue-100 text-blue-800 rounded">
              {groupPrefix}
            </span>
          )}
        </div>
        <div className="text-right">
          <select
            value={selectedMetric}
            onChange={(e) => setSelectedMetric(e.target.value as ChartMetric)}
            className="px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value="offered">Offered</option>
            <option value="answered">Answered</option>
            <option value="abandoned">Abandoned (No VM)</option>
            <option value="service_level">Service Level %</option>
            <option value="asa">ASA</option>
            <option value="aht">AHT</option>
            <option value="mos">MOS</option>
          </select>
        </div>
      </div>

      {/* KPI Tiles */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <div className="bg-blue-50 p-3 rounded-lg">
          <div className="text-xs font-medium text-blue-600 mb-1">Offered</div>
          <div className="text-xl font-bold text-gray-900">{formatCount(metrics.offered.value)}</div>
        </div>
        <div className="bg-green-50 p-3 rounded-lg">
          <div className="text-xs font-medium text-green-600 mb-1">Answered</div>
          <div className="text-xl font-bold text-gray-900">{formatCount(metrics.answered.value)}</div>
        </div>
        <div className="bg-red-50 p-3 rounded-lg">
          <div className="text-xs font-medium text-red-600 mb-1">Abandoned (No VM)</div>
          <div className="text-xl font-bold text-gray-900">{formatCount(metrics.abandoned.value)}</div>
        </div>
        <div className="bg-amber-50 p-3 rounded-lg">
          <div className="text-xs font-medium text-amber-700 mb-1">Voicemail</div>
          <div className="text-xl font-bold text-gray-900">{formatCount(metrics.voicemail_calls?.value ?? 0)}</div>
        </div>
        <div className="bg-rose-50 p-3 rounded-lg">
          <div className="text-xs font-medium text-rose-700 mb-1">Missed</div>
          <div className="text-xl font-bold text-gray-900">{formatCount(metrics.missed_calls?.value ?? 0)}</div>
        </div>
        <div className="bg-purple-50 p-3 rounded-lg">
          <div className="text-xs font-medium text-purple-600 mb-1">SL (30s)</div>
          <div className="text-xl font-bold text-gray-900">{formatPercentage(metrics.service_level.value)}</div>
        </div>
        <div className="bg-yellow-50 p-3 rounded-lg">
          <div className="text-xs font-medium text-amber-600 mb-1">ASA</div>
          <div className="text-xl font-bold text-gray-900">{formatSecondsToTime(metrics.asa_avg.value)}</div>
        </div>
        <div className="bg-cyan-50 p-3 rounded-lg">
          <div className="text-xs font-medium text-cyan-600 mb-1">AHT</div>
          <div className="text-xl font-bold text-gray-900">{formatSecondsToTime(metrics.aht_avg.value)}</div>
        </div>
        <div className="bg-pink-50 p-3 rounded-lg">
          <div className="text-xs font-medium text-pink-600 mb-1">MOS</div>
          <div className="text-xl font-bold text-gray-900">{formatMOS(metrics.mos_avg.value)}</div>
        </div>
        <div className="bg-gray-50 p-3 rounded-lg">
          <div className="text-xs font-medium text-gray-600 mb-1">Answer %</div>
          <div className="text-xl font-bold text-gray-900">{formatPercentage(metrics.answer_rate.value)}</div>
        </div>
      </div>

      {/* Line Chart */}
      <div>
        <h4 className="text-sm font-semibold text-gray-700 mb-3">
          {currentConfig.label} Trend (Hourly)
        </h4>
        <ResponsiveContainer width="100%" height={250}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
            <XAxis
              dataKey="displayTime"
              tick={{ fontSize: 11 }}
              interval="preserveStartEnd"
              minTickGap={40}
            />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip content={customTooltip} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Line
              type="monotone"
              dataKey="value"
              stroke={currentConfig.color}
              strokeWidth={2}
              name={currentConfig.label}
              dot={false}
              connectNulls={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      {/* Empty state for chart */}
      {hourly.length === 0 && (
        <div className="text-center py-8 text-gray-500">
          No hourly data available for this queue
        </div>
      )}
    </div>
  );
}
