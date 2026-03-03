import { addHours, format, parseISO } from 'date-fns';
import type { QueuePerformanceHourlyData, HourlyMetrics, GroupedQueue } from '../types';

/**
 * Group queues by the first 3 letters of the queue name
 * Example: "TSW-Sales" and "TSW-Support" both get grouped under "TSW"
 */
export function groupQueuesByPrefix(queues: QueuePerformanceHourlyData[]): GroupedQueue[] {
  const groups = new Map<string, QueuePerformanceHourlyData[]>();

  queues.forEach((queue) => {
    // Extract first 3 letters (or full name if shorter)
    const groupKey = queue.queue_name.trim().slice(0, 3).toUpperCase();
    
    if (!groups.has(groupKey)) {
      groups.set(groupKey, []);
    }
    groups.get(groupKey)!.push(queue);
  });

  // Convert map to array and sort by group key
  return Array.from(groups.entries())
    .map(([groupKey, queues]) => ({
      groupKey,
      queues: queues.sort((a, b) => a.queue_name.localeCompare(b.queue_name)),
    }))
    .sort((a, b) => a.groupKey.localeCompare(b.groupKey));
}

/**
 * Generate a complete hourly timeline from start to end date
 * Returns array of ISO timestamp strings for each hour bucket
 */
export function generateHourlyTimeline(startDate: Date, endDate: Date): string[] {
  const timeline: string[] = [];
  let current = new Date(startDate);
  current.setMinutes(0, 0, 0); // Round down to hour

  const end = new Date(endDate);
  end.setMinutes(0, 0, 0); // Round down to hour

  while (current <= end) {
    timeline.push(current.toISOString());
    current = addHours(current, 1);
  }

  return timeline;
}

/**
 * Fill missing hourly buckets with default values
 * Ensures every hour in the timeline has a data point
 */
export function fillMissingHourlyBuckets(
  hourlyData: HourlyMetrics[],
  timeline: string[]
): HourlyMetrics[] {
  // Create a map of existing data points by timestamp
  const dataMap = new Map<string, HourlyMetrics>();
  hourlyData.forEach((point) => {
    // Normalize timestamp to hour bucket
    const hourBucket = new Date(point.timestamp);
    hourBucket.setMinutes(0, 0, 0);
    dataMap.set(hourBucket.toISOString(), point);
  });

  // Fill in missing buckets
  return timeline.map((timestamp) => {
    if (dataMap.has(timestamp)) {
      return dataMap.get(timestamp)!;
    }

    // Return default values for missing buckets
    return {
      timestamp,
      offered: 0,
      answered: 0,
      abandoned: 0,
      service_level: 0, // 0% if no calls
      asa: null, // null indicates no data
      aht: null,
      mos: null,
    };
  });
}

/**
 * Format seconds to mm:ss or ss if less than 60 seconds
 */
export function formatSecondsToTime(seconds: number | null): string {
  if (seconds === null || seconds === undefined) {
    return 'N/A';
  }

  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${minutes}:${secs.toString().padStart(2, '0')}`;
}

/**
 * Format MOS score (0-5 scale) to 2 decimal places
 */
export function formatMOS(mos: number | null): string {
  if (mos === null || mos === undefined) {
    return 'N/A';
  }
  return mos.toFixed(2);
}

/**
 * Format percentage to 1 decimal place
 */
export function formatPercentage(value: number | null): string {
  if (value === null || value === undefined) {
    return 'N/A';
  }
  return `${value.toFixed(1)}%`;
}

/**
 * Format count with thousands separator
 */
export function formatCount(value: number): string {
  return new Intl.NumberFormat('en-US').format(value);
}

/**
 * Format hourly timestamp for chart display
 */
export function formatHourlyTimestamp(timestamp: string, showDate: boolean = true): string {
  const date = parseISO(timestamp);
  if (showDate) {
    return format(date, 'MMM dd, HH:mm');
  }
  return format(date, 'HH:mm');
}

/**
 * Calculate average from hourly data points (excluding null values)
 */
export function calculateAverageFromHourly(
  hourlyData: HourlyMetrics[],
  metric: 'asa' | 'aht' | 'mos'
): number | null {
  const validValues = hourlyData
    .map((h) => h[metric])
    .filter((v): v is number => v !== null && !isNaN(v));

  if (validValues.length === 0) {
    return null;
  }

  const sum = validValues.reduce((acc, val) => acc + val, 0);
  return sum / validValues.length;
}
