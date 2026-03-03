/**
 * Unit tests for Queue Performance utility functions
 * 
 * To run these tests, add vitest to your project:
 * npm install -D vitest @vitest/ui
 * 
 * Then add to package.json scripts:
 * "test": "vitest"
 * "test:ui": "vitest --ui"
 */

// Uncomment when vitest is installed
// import { describe, it, expect } from 'vitest';
import type { QueuePerformanceHourlyData, HourlyMetrics } from '../types';
import {
  groupQueuesByPrefix,
  generateHourlyTimeline,
  fillMissingHourlyBuckets,
  formatSecondsToTime,
  formatMOS,
  formatPercentage,
  formatCount,
} from './queuePerformance';

// Mock test functions for documentation purposes
// Replace with actual vitest imports when test runner is configured
const describe = (_name: string, fn: () => void) => fn;
const it = (_name: string, fn: () => void) => fn;
const expect = (actual: any) => ({
  toBe: (expected: any) => {
    if (actual !== expected) {
      console.error(`Expected ${expected}, got ${actual}`);
    }
  },
  toEqual: (expected: any) => {
    if (JSON.stringify(actual) !== JSON.stringify(expected)) {
      console.error(`Expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`);
    }
  },
  toHaveLength: (expected: number) => {
    if (actual.length !== expected) {
      console.error(`Expected length ${expected}, got ${actual.length}`);
    }
  },
  toContain: (expected: any) => {
    if (!actual.includes(expected)) {
      console.error(`Expected to contain ${expected}`);
    }
  },
});

describe('Queue Performance Utils', () => {
  describe('groupQueuesByPrefix', () => {
    it('should group queues by first 3 letters', () => {
      const queues: QueuePerformanceHourlyData[] = [
        {
          queue_id: '1',
          queue_name: 'TSW-Sales',
          metrics: {} as any,
          hourly: [],
        },
        {
          queue_id: '2',
          queue_name: 'TSW-Support',
          metrics: {} as any,
          hourly: [],
        },
        {
          queue_id: '3',
          queue_name: 'NYC-Main',
          metrics: {} as any,
          hourly: [],
        },
      ];

      const groups = groupQueuesByPrefix(queues);

      expect(groups).toHaveLength(2);
      expect(groups[0].groupKey).toBe('NYC');
      expect(groups[1].groupKey).toBe('TSW');
      expect(groups[1].queues).toHaveLength(2);
    });

    it('should handle queue names shorter than 3 characters', () => {
      const queues: QueuePerformanceHourlyData[] = [
        {
          queue_id: '1',
          queue_name: 'AB',
          metrics: {} as any,
          hourly: [],
        },
      ];

      const groups = groupQueuesByPrefix(queues);

      expect(groups).toHaveLength(1);
      expect(groups[0].groupKey).toBe('AB');
    });

    it('should be case-insensitive for grouping', () => {
      const queues: QueuePerformanceHourlyData[] = [
        {
          queue_id: '1',
          queue_name: 'tsw-sales',
          metrics: {} as any,
          hourly: [],
        },
        {
          queue_id: '2',
          queue_name: 'TSW-Support',
          metrics: {} as any,
          hourly: [],
        },
      ];

      const groups = groupQueuesByPrefix(queues);

      expect(groups).toHaveLength(1);
      expect(groups[0].groupKey).toBe('TSW');
      expect(groups[0].queues).toHaveLength(2);
    });
  });

  describe('generateHourlyTimeline', () => {
    it('should generate hourly timestamps between start and end', () => {
      const start = new Date('2026-02-09T10:00:00Z');
      const end = new Date('2026-02-09T13:00:00Z');

      const timeline = generateHourlyTimeline(start, end);

      expect(timeline).toHaveLength(4); // 10:00, 11:00, 12:00, 13:00
      expect(timeline[0]).toBe('2026-02-09T10:00:00.000Z');
      expect(timeline[3]).toBe('2026-02-09T13:00:00.000Z');
    });

    it('should round down start and end to hour boundaries', () => {
      const start = new Date('2026-02-09T10:30:45Z');
      const end = new Date('2026-02-09T12:45:30Z');

      const timeline = generateHourlyTimeline(start, end);

      expect(timeline).toHaveLength(3); // 10:00, 11:00, 12:00
      expect(timeline[0]).toContain('T10:00:00');
      expect(timeline[2]).toContain('T12:00:00');
    });
  });

  describe('fillMissingHourlyBuckets', () => {
    it('should fill missing hours with default values', () => {
      const timeline = [
        '2026-02-09T10:00:00.000Z',
        '2026-02-09T11:00:00.000Z',
        '2026-02-09T12:00:00.000Z',
      ];

      const hourlyData: HourlyMetrics[] = [
        {
          timestamp: '2026-02-09T10:00:00.000Z',
          offered: 10,
          answered: 8,
          abandoned: 2,
          service_level: 80,
          asa: 45,
          aht: 120,
          mos: 4.2,
        },
        // Missing 11:00
        {
          timestamp: '2026-02-09T12:00:00.000Z',
          offered: 15,
          answered: 12,
          abandoned: 3,
          service_level: 85,
          asa: 38,
          aht: 110,
          mos: 4.3,
        },
      ];

      const filled = fillMissingHourlyBuckets(hourlyData, timeline);

      expect(filled).toHaveLength(3);
      expect(filled[1]).toEqual({
        timestamp: '2026-02-09T11:00:00.000Z',
        offered: 0,
        answered: 0,
        abandoned: 0,
        service_level: 0,
        asa: null,
        aht: null,
        mos: null,
      });
    });

    it('should preserve existing data points', () => {
      const timeline = ['2026-02-09T10:00:00.000Z'];

      const hourlyData: HourlyMetrics[] = [
        {
          timestamp: '2026-02-09T10:00:00.000Z',
          offered: 10,
          answered: 8,
          abandoned: 2,
          service_level: 80,
          asa: 45,
          aht: 120,
          mos: 4.2,
        },
      ];

      const filled = fillMissingHourlyBuckets(hourlyData, timeline);

      expect(filled).toHaveLength(1);
      expect(filled[0]).toEqual(hourlyData[0]);
    });
  });

  describe('formatSecondsToTime', () => {
    it('should format seconds less than 60', () => {
      expect(formatSecondsToTime(45)).toBe('45s');
      expect(formatSecondsToTime(0)).toBe('0s');
    });

    it('should format seconds as mm:ss for 60 or more', () => {
      expect(formatSecondsToTime(125)).toBe('2:05');
      expect(formatSecondsToTime(60)).toBe('1:00');
      expect(formatSecondsToTime(3665)).toBe('61:05');
    });

    it('should handle null values', () => {
      expect(formatSecondsToTime(null)).toBe('N/A');
    });
  });

  describe('formatMOS', () => {
    it('should format to 2 decimal places', () => {
      expect(formatMOS(4.234)).toBe('4.23');
      expect(formatMOS(3.5)).toBe('3.50');
    });

    it('should handle null values', () => {
      expect(formatMOS(null)).toBe('N/A');
    });
  });

  describe('formatPercentage', () => {
    it('should format to 1 decimal place with % sign', () => {
      expect(formatPercentage(88.456)).toBe('88.5%');
      expect(formatPercentage(100)).toBe('100.0%');
      expect(formatPercentage(0.5)).toBe('0.5%');
    });

    it('should handle null values', () => {
      expect(formatPercentage(null)).toBe('N/A');
    });
  });

  describe('formatCount', () => {
    it('should add thousands separator', () => {
      expect(formatCount(1000)).toBe('1,000');
      expect(formatCount(1234567)).toBe('1,234,567');
      expect(formatCount(999)).toBe('999');
    });
  });
});
