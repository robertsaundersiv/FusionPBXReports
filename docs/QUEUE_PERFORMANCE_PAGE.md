# Queue Performance Page - Documentation

## Overview

The Queue Performance page provides detailed, hourly-bucketed call queue metrics with prefix-based grouping for easy comparison of related queues. It supports date range filtering, multi-queue selection, and interactive visualizations.

## Features Implemented

### ✅ Must-Have Features

1. **Top-of-Page Filters**
   - Date range picker with presets (Today, Yesterday, Last 7 days, Last 30 days, Custom)
   - Multi-select queue selector (searchable, shows count)
   - Direction filter (All, Inbound, Outbound)
   - Auto-apply with debounce
   - Filters synced with URL query params (for sharing)

2. **Default View**
   - All queues selected by default
   - Last 7 days time range
   - Hourly time buckets

3. **Queue Cards (One Per Queue)**
   Each card displays:
   - **Offered** - Total calls entering queue
   - **Answered** - Calls answered by agents
   - **Abandoned** - Calls that abandoned (excluding deflect-to-VM/external per backend logic)
   - **Service Level (30 sec)** - % of calls answered within 30 seconds
   - **ASA** - Average Speed of Answer (time to answer)
   - **AHT** - Average Handle Time (talk time + hold time)
   - **MOS** - Mean Opinion Score (call quality, 0-5 scale)
   - **Answer %** - Percentage of offered calls that were answered
   - **Line Chart** - Hourly trend visualization with selectable metric

4. **Prefix-Based Grouping**
   - Queues grouped by first 3 letters of name
   - Example: "TSW-Sales", "TSW-Support" → grouped under "TSW"
   - Collapsible group sections
   - Expand/Collapse all functionality
   - Visual group badges on cards

### 📊 Data Visualization

- **Hourly Time Series Charts**
  - Line charts showing trends over time
  - Metric selector dropdown per card (Offered/Answered/Abandoned/SL/ASA/AHT/MOS)
  - Smart tooltip formatting based on metric type
  - Auto-scaling axes
  - Responsive design

- **KPI Tiles**
  - Color-coded by metric category
  - Large, readable values
  - Consistent formatting (counts, %, time, MOS)

### 🎨 UX Features

- **Loading States**
  - Skeleton loader during data fetch
  - Inline spinner with message

- **Error Handling**
  - Error banner with clear message
  - Retry button
  - Fallback to last good data

- **Empty States**
  - "No data" message when filters return no results
  - Suggestions to adjust filters

- **Last Updated Timestamp**
  - Shows when data was last refreshed
  - Useful for monitoring data freshness

## File Structure

```
frontend/src/
├── pages/
│   └── QueuePerformance.tsx          # Main page component
├── components/
│   ├── QueuePerformanceCard.tsx      # Individual queue card with chart
│   └── DashboardFilterBar.tsx        # (reused from Executive Overview)
├── services/
│   └── dashboard.ts                  # API service (getQueuePerformance)
├── types/
│   └── index.ts                      # TypeScript interfaces
└── utils/
    └── queuePerformance.ts           # Grouping, timeline fill, formatting utilities
```

## Data Flow

### 1. Frontend to Backend

**Request:**
```
GET /api/v1/dashboard/queue-performance?start_date=2026-02-09&end_date=2026-02-16&queue_ids=uuid1,uuid2
```

**Parameters:**
- `start_date` (ISO string) - Start of date range
- `end_date` (ISO string) - End of date range
- `queue_ids` (array) - Optional list of queue UUIDs (empty = all queues)
- `direction` (string) - Optional: 'inbound', 'outbound', or omit for all

### 2. Expected Backend Response

The frontend expects the backend to return:

```typescript
{
  "queues": [
    {
      "queue_id": "uuid-1234",
      "queue_name": "TSW-Sales",
      "metrics": {
        "offered": { "value": 1250, "unit": "calls" },
        "answered": { "value": 1100, "unit": "calls" },
        "abandoned": { "value": 150, "unit": "calls" },
        "answer_rate": { "value": 88.0, "unit": "%" },
        "abandon_rate": { "value": 12.0, "unit": "%" },
        "asa_avg": { "value": 45.2, "unit": "seconds" },
        "aht_avg": { "value": 180.5, "unit": "seconds" },
        "service_level": { "value": 72.3, "unit": "%" },
        "mos_avg": { "value": 4.2, "unit": "" }
      },
      "hourly": [
        {
          "timestamp": "2026-02-09T00:00:00Z",
          "offered": 12,
          "answered": 10,
          "abandoned": 2,
          "service_level": 80.0,
          "asa": 38.5,
          "aht": 165.2,
          "mos": 4.3
        },
        {
          "timestamp": "2026-02-09T01:00:00Z",
          "offered": 8,
          "answered": 7,
          "abandoned": 1,
          "service_level": 85.7,
          "asa": 42.1,
          "aht": 172.8,
          "mos": 4.1
        }
        // ... hourly buckets for entire date range
      ]
    }
    // ... more queues
  ]
}
```

**⚠️ Important Notes:**
- **Hourly buckets** must cover the entire date range (start to end)
- Missing hours should be filled with zeros/nulls by frontend (handled automatically)
- **ASA/AHT/MOS** can be `null` for hours with no calls
- **Timestamps** must be ISO 8601 format, aligned to hour boundaries

### 3. Frontend Data Processing

The frontend performs these transformations:

1. **Timeline Generation**
   - Generates complete hourly timeline from start to end date
   - Ensures no gaps in X-axis

2. **Missing Bucket Fill**
   - Fills missing hours with default values:
     - Counts (offered/answered/abandoned): `0`
     - Rates (service_level): `0%`
     - Averages (asa/aht/mos): `null` (shown as "N/A")

3. **Prefix Grouping**
   - Extracts first 3 characters from queue name
   - Groups queues by prefix
   - Sorts groups alphabetically

4. **Formatting**
   - Counts: thousands separator (1,250)
   - Percentages: 1 decimal (88.0%)
   - Seconds: mm:ss format (3:45) or ss if <60 (45s)
   - MOS: 2 decimals (4.23)

## Backend Modification Required

### Current State
The existing `/api/v1/dashboard/queue-performance` endpoint returns:
- Aggregate metrics per queue
- Heatmaps (hour-of-day × day-of-week)
- Breakdowns (hangup causes, outcomes)

### Needed Enhancement
Add **hourly time series data** to the response:

```python
# In backend/app/api/dashboard.py

# Add hourly aggregation query
hourly_query = db.query(
    func.date_trunc('hour', func.to_timestamp(CDRRecord.start_epoch)).label('hour_bucket'),
    func.count(func.distinct(...)).label('offered'),
    func.sum(case((CDRRecord.cc_queue_answered_epoch.isnot(None), 1), else_=0)).label('answered'),
    # ... other metrics
).filter(
    CDRRecord.start_epoch >= start_epoch,
    CDRRecord.start_epoch <= end_epoch,
    CDRRecord.cc_queue.like(f"{queue_extension}@%"),
).group_by('hour_bucket').order_by('hour_bucket').all()

# Format into response
hourly_data = [
    {
        "timestamp": row.hour_bucket.isoformat(),
        "offered": row.offered,
        "answered": row.answered,
        "abandoned": row.abandoned,
        "service_level": calculate_sl(row),
        "asa": row.avg_asa,
        "aht": row.avg_aht,
        "mos": row.avg_mos,
    }
    for row in hourly_query
]

queue_result["hourly"] = hourly_data
```

## Utility Functions

### `groupQueuesByPrefix(queues)`
Groups queue data by first 3 letters of queue name.

**Example:**
```typescript
Input: [
  { queue_name: "TSW-Sales", ... },
  { queue_name: "TSW-Support", ... },
  { queue_name: "NYO-Main", ... }
]

Output: [
  {
    groupKey: "TSW",
    queues: [
      { queue_name: "TSW-Sales", ... },
      { queue_name: "TSW-Support", ... }
    ]
  },
  {
    groupKey: "NYO",
    queues: [{ queue_name: "NYO-Main", ... }]
  }
]
```

### `generateHourlyTimeline(startDate, endDate)`
Generates array of ISO timestamps for every hour between start and end.

### `fillMissingHourlyBuckets(hourlyData, timeline)`
Ensures every hour in timeline has a data point, filling missing with defaults.

### Formatting Functions
- `formatCount(n)` - Adds thousands separator
- `formatPercentage(n)` - Shows 1 decimal with % sign
- `formatSecondsToTime(n)` - Converts to mm:ss or ss
- `formatMOS(n)` - Shows 2 decimals
- `formatHourlyTimestamp(iso)` - Formats for chart display

## Component Architecture

### `QueuePerformance.tsx`
**Purpose:** Main page container  
**Responsibilities:**
- Manages filters via useFilterStore
- Fetches data from API
- Processes data (timeline fill, grouping)
- Renders grouped sections
- Handles loading/error/empty states

### `QueuePerformanceCard.tsx`
**Purpose:** Individual queue visualization  
**Props:**
- `queueData: QueuePerformanceHourlyData` - Queue metrics and hourly data
- `groupPrefix?: string` - Optional group badge text

**Features:**
- 8 KPI tiles (color-coded)
- Metric selector dropdown
- Line chart with hourly trend
- Smart tooltip formatting
- Responsive grid layout

### `DashboardFilterBar.tsx` (Reused)
**Purpose:** Shared filter component  
**Features:**
- Date range presets
- Multi-select queue picker
- Direction selector
- Auto-save to URL params

## Testing Recommendations

### Unit Tests

1. **Grouping Logic**
```typescript
test('groupQueuesByPrefix - groups correctly', () => {
  const queues = [
    { queue_name: 'TSW-Sales', ... },
    { queue_name: 'TSW-Support', ... },
    { queue_name: 'NYC-Main', ... }
  ];
  const groups = groupQueuesByPrefix(queues);
  expect(groups).toHaveLength(2);
  expect(groups[0].groupKey).toBe('TSW');
  expect(groups[0].queues).toHaveLength(2);
});
```

2. **Timeline Fill**
```typescript
test('fillMissingHourlyBuckets - fills gaps', () => {
  const timeline = ['2026-02-09T00:00:00Z', '2026-02-09T01:00:00Z', '2026-02-09T02:00:00Z'];
  const data = [
    { timestamp: '2026-02-09T00:00:00Z', offered: 10, ... },
    // Missing 01:00
    { timestamp: '2026-02-09T02:00:00Z', offered: 15, ... }
  ];
  const filled = fillMissingHourlyBuckets(data, timeline);
  expect(filled).toHaveLength(3);
  expect(filled[1].offered).toBe(0); // Filled missing hour
});
```

3. **Formatting**
```typescript
test('formatSecondsToTime - formats correctly', () => {
  expect(formatSecondsToTime(45)).toBe('45s');
  expect(formatSecondsToTime(125)).toBe('2:05');
  expect(formatSecondsToTime(null)).toBe('N/A');
});
```

### Integration Tests

1. Render with empty data
2. Render with single queue
3. Render with multiple groups
4. Filter changes trigger re-fetch
5. Error state displays correctly

## Performance Considerations

### Frontend Optimizations

1. **Memoization**
   - `useMemo` for grouping computation
   - Prevents re-grouping on every render

2. **Lazy Loading**
   - Page loaded lazily via React.lazy()
   - Reduces initial bundle size

3. **Virtualization** (Future)
   - If queue count >50, consider react-window for card list

4. **Request Cancellation**
   - AbortController to cancel pending requests on filter change

### Backend Optimizations

1. **Indexing**
   - Ensure indexes on: `start_epoch`, `cc_queue`, `direction`
   - Compound index: `(start_epoch, cc_queue)` for queue-specific queries

2. **Caching**
   - Consider Redis cache for frequently-accessed date ranges
   - Cache key: `queue_perf:{queue_ids}:{start}:{end}:{direction}`
   - TTL: 5-15 minutes (balance freshness vs. performance)

3. **Aggregation Strategy**
   - If data volume is high, use pre-aggregated `HourlyAggregate` table
   - Fallback to raw CDR for recent hours not yet aggregated

## Acceptance Criteria

- [x] Page exists in navigation and loads without errors
- [x] Default filters show all queues and last 7 days
- [x] Filters work (date range + multi-select queues + direction)
- [x] Queues render as cards, grouped by first 3 letters
- [x] Each card shows 7 KPIs: Offered/Answered/Abandoned/SL30/ASA/AHT/MOS
- [x] Each card shows a line chart with hourly trend points
- [x] Missing hourly buckets are handled gracefully
- [x] Clear loading, empty, and error states
- [x] Formatting rules applied (%, mm:ss, decimals, thousands separator)
- [ ] Backend endpoint returns hourly time series data (requires backend modification)

## Future Enhancements

### Short-term
1. **Export to CSV** - Download queue performance data
2. **Comparison Mode** - Side-by-side comparison of 2-4 queues
3. **Alerts** - Highlight queues exceeding abandon rate threshold

### Long-term
1. **Real-time Updates** - WebSocket for live metrics
2. **Custom Grouping** - User-defined queue groups beyond prefix
3. **Forecasting** - Predict queue volume based on historical patterns
4. **Drill-down** - Click queue card to see individual call details

## Troubleshooting

### Issue: No data showing
**Check:**
1. Backend endpoint responding correctly (`/api/v1/dashboard/queue-performance`)
2. Date range has data (try last 30 days)
3. Queue filters not over-restricted
4. Browser console for network errors

### Issue: Chart not displaying
**Check:**
1. `hourly` array present in API response
2. Timestamps in ISO format
3. Browser console for React errors

### Issue: Grouping not working
**Check:**
1. Queue names have at least 1 character
2. Console log `groupedQueues` to debug grouping logic

## Support

For questions or issues:
- Check browser console for errors
- Review API response format in Network tab
- Verify backend logs for query errors
- Contact: team@phonereports.com
