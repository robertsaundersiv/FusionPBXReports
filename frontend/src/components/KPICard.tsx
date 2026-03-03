import type { KPIMetric } from '../types';
import { TrendingUp, TrendingDown, Info } from 'lucide-react';
import { numberUtils } from '../utils/formatters';

interface KPICardProps {
  metric: KPIMetric;
  onDefinitionClick?: () => void;
}

export default function KPICard({ metric, onDefinitionClick }: KPICardProps) {
  const isNegativeTrend = metric.unit === '%' && (metric.name.includes('Abandon') || metric.name.includes('Bad'));
  const isTrendPositive = !isNegativeTrend ? (metric.trend ?? 0) > 0 : (metric.trend ?? 0) < 0;

  const getThresholdColor = () => {
    if (!metric.threshold) return 'text-gray-700';
    if (metric.value >= metric.threshold.good) return 'text-green-600';
    if (metric.value >= metric.threshold.warning) return 'text-yellow-600';
    return 'text-red-600';
  };

  return (
    <div className="kpi-card">
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-sm text-gray-600">{metric.name}</p>
          <p className={`text-3xl font-bold ${getThresholdColor()}`}>
            {typeof metric.value === 'number' && metric.value >= 1000
              ? numberUtils.abbreviateNumber(metric.value)
              : metric.value.toFixed(metric.unit === '%' ? 1 : 0)}{' '}
            <span className="text-lg text-gray-500">{metric.unit}</span>
          </p>
        </div>
        <button
          onClick={onDefinitionClick}
          className="p-1 text-gray-400 hover:text-gray-600 transition-colors"
          title="View definition"
        >
          <Info size={20} />
        </button>
      </div>

      {metric.trend !== undefined && (
        <div className="flex items-center space-x-1 text-sm">
          {isTrendPositive ? (
            <TrendingUp size={16} className="text-green-600" />
          ) : (
            <TrendingDown size={16} className="text-red-600" />
          )}
          <span className={isTrendPositive ? 'text-green-600' : 'text-red-600'}>
            {isTrendPositive ? '+' : ''}{metric.trend.toFixed(1)}%
          </span>
          <span className="text-gray-500">vs. previous period</span>
        </div>
      )}
    </div>
  );
}
