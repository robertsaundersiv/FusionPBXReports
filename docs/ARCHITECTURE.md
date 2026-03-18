# Architecture Overview

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         End Users                               │
│                  (Browsers via HTTPS)                           │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    Nginx Reverse Proxy                          │
│            (SSL/TLS, Routing, Compression)                      │
└────────────────────────────┬────────────────────────────────────┘
            │                                    │
┌───────────▼──────────────┐        ┌───────────▼──────────────┐
│   Frontend Application   │        │   Backend API Server     │
│      (React/TypeScript)  │        │     (FastAPI)            │
│   Port: 3000 (dev)       │        │     Port: 8000           │
│                          │        │                          │
│ - Dashboard UI           │        │ - REST API endpoints     │
│ - Interactive charts     │        │ - Authentication         │
│ - Global filtering       │        │ - Business logic         │
│ - Call drilldowns        │        │ - KPI calculation        │
│ - CSV export             │        │ - User management        │
└──────────────────────────┘        └───────────┬──────────────┘
                                                 │
                    ┌────────────────────────────┴─────────────────┐
                    │                                               │
        ┌───────────▼──────────────┐         ┌────────────────────▼──┐
        │   PostgreSQL Database    │         │  Background Worker    │
        │   - CDR Records          │         │  (Celery + Redis)     │
        │   - Queues/Agents        │         │                       │
        │   - Aggregates           │         │ - CDR ingestion       │
        │   - Users                │         │ - Metadata sync       │
        │   - Reports              │         │ - Aggregation jobs    │
        │   - Config               │         │ - Report generation   │
        └──────────────────────────┘         └───────────┬───────────┘
                                                         │
                                            ┌────────────▼───────────┐
                                            │   Redis Cache/Queue    │
                                            │   - Task queue         │
                                            │   - Result store       │
                                            └────────────────────────┘
        ┌──────────────────────────────────────────┐
        │  FusionPBX External API                  │
        │  - /app/api/7/xml_cdr                   │
        │  - /app/api/7/call_center_queues        │
        │  - /app/api/7/call_center_agents        │
        │  - /app/api/7/call_center_tiers         │
        │  - /app/api/7/extensions                │
        └──────────────────────────────────────────┘
```

## Data Flow

### Inbound Call Data Flow

```
1. Call occurs in FusionPBX
   │
   └─► CDR recorded in FusionPBX database
       │
       └─► ETL Worker polls /app/api/7/xml_cdr (every 5 min)
           │
           ├─► Upsert by xml_cdr_uuid (idempotent)
           │
           ├─► Update watermark
           │
           └─► Trigger hourly aggregation
               │
               ├─► HourlyAggregate computed (every 15 min)
               │
               └─► DailyAggregate computed (daily @ 6am UTC)
                   │
                   └─► Dashboard queries use aggregates
                       │
                       └─► User sees KPIs in < 2 seconds
```

### Metadata Synchronization

```
Queue/Agent Sync (Hourly):
- Fetch from FusionPBX APIs
- Update Queue table with friendly names
- Update Agent table
- Maintain AgentQueueTier membership
- Cache for API responses
```

### Report Generation

```
ScheduledReport Configuration:
  ├─ Daily Ops Summary
  ├─ Weekly Performance Pack
  ├─ Monthly Leadership Summary
  └─ SLA Compliance Report
     │
     └─► Generate PDF/CSV at scheduled time
         │
         └─► Send via email/Slack webhook
```

## Component Details

### Frontend (React/TypeScript)
- **Framework**: React 18 + TypeScript + Vite
- **State Management**: Zustand for filters
- **Charts**: Recharts for visualizations
- **Styling**: Tailwind CSS
- **Features**:
  - Server-side pagination for call tables
  - Responsive dashboard layout
  - Real-time filter synchronization
  - CSV export functionality
  - Role-based number masking

### Backend (FastAPI)
- **Framework**: FastAPI with Pydantic validation
- **Database**: SQLAlchemy ORM + PostgreSQL
- **Authentication**: JWT tokens with role-based access
- **APIs**:
  - `/api/v1/auth/*` - Authentication
  - `/api/v1/cdr/*` - Call records
  - `/api/v1/dashboard/*` - Dashboard data
  - `/api/v1/admin/*` - Administration
- **Performance**: Pre-computed aggregates, efficient indexing

### Worker (Celery)
- **Task Queue**: Redis-backed
- **Scheduler**: Celery Beat for periodic tasks
- **Tasks**:
  - `ingest_cdr_records` - every 5 minutes
  - `sync_queue_metadata` - hourly
  - `sync_agent_metadata` - hourly
  - `compute_hourly_aggregates` - every 15 minutes
  - `compute_daily_aggregates` - daily @ 6am UTC
  - `generate_scheduled_reports` - configured schedule
- **Idempotency**: All tasks safe for rerun

### Database Schema
- **CDRRecord** - Raw call detail records (~1M+ records typical)
- **Queue** - Queue metadata and configuration
- **Agent** - Agent metadata
- **AgentQueueTier** - Agent↔Queue membership mapping
- **HourlyAggregate** - Pre-computed hourly metrics
- **DailyAggregate** - Pre-computed daily metrics
- **User** - Dashboard user accounts
- **ScheduledReport** - Report configurations
- **ETLPipelineStatus** - Watermarks and sync status
- **OperationalNote** - Manager notes
- **Extension** - User→Extension mappings

### Reverse Proxy (Nginx)
- **SSL/TLS Termination**: HTTPS encryption
- **Request Routing**: Frontend / API separation
- **Compression**: Gzip for bandwidth
- **Security Headers**: HSTS, X-Frame-Options, etc.
- **Health Checks**: `/health` endpoint monitoring

## Deployment Models

### Development (Windows)
```bash
docker compose up
```
- All services in containers
- Hot-reload enabled for code changes
- Database persists in named volumes
- No SSL required

### Production (Ubuntu)
```bash
docker compose up -d
```
- Same compose file (compatibility)
- SSL certificates configured
- Environment=production
- Resource limits set
- Log rotation configured
- Monitoring hooks added

## Security Layers

1. **Authentication**: JWT tokens with expiration
2. **Authorization**: Role-based access control
3. **Data Masking**: Caller numbers masked by role
4. **Encryption**: TLS for all data in transit
5. **Database**: Connection pooling, prepared statements
6. **API**: Input validation via Pydantic
7. **Secrets**: Environment variables, Docker secrets

## Performance Characteristics

| Metric | Target | Achievable |
|--------|--------|------------|
| Dashboard load time | < 2s | ✓ (via aggregates) |
| CDR search (1M records) | < 5s | ✓ (indexed queries) |
| 10K+ calls/day ingest | Real-time | ✓ (incremental) |
| Concurrent users | 50+ | ✓ (stateless API) |
| Data freshness | 15 min | ✓ (hourly agg) |

## Scalability Considerations

### Vertical Scaling
- Increase PostgreSQL `shared_buffers`
- Increase worker concurrency
- Increase Redis memory

### Horizontal Scaling
- Run multiple backend instances behind load balancer
- Run multiple workers for parallel task processing
- Use read replicas for reports database

### Data Retention
- Default: Keep raw CDR for 90 days
- Aggregates kept for 2 years
- Configurable via retention policy

## Monitoring & Observability

### Available Metrics
- ETL pipeline status
- Database query performance
- API response times
- Worker task execution
- Error rates

### Log Aggregation Points
- `/var/log/docker/` - Container logs
- `docker compose logs` - Real-time streaming
- Application structured logging with timestamps

### Health Checks
- Database connectivity
- Redis connectivity
- FusionPBX API reachability
- Endpoint: `GET /health`
