# FusionPBX Analytics Dashboard

A comprehensive call center analytics and reporting solution for FusionPBX. This system provides executive dashboards, agent performance tracking, quality metrics, and scheduled reporting with support for Windows development and Ubuntu production deployment via Docker Compose.

## Features

### Dashboards

- **Executive Overview** - High-level KPIs, trends, and operational metrics
- **Queue Performance** - Hourly-bucketed queue metrics with prefix-based grouping, interactive charts, and 7 key KPIs per queue (Offered, Answered, Abandoned, Service Level, ASA, AHT, MOS). See [docs/QUEUE_PERFORMANCE_PAGE.md](docs/QUEUE_PERFORMANCE_PAGE.md) for details.
- **Agent Performance & Coaching** - Agent leaderboards and coaching insights
- **Quality & Telecom Health** - MOS, codec distribution, failure analysis
- **Repeat Callers & Customer Experience** - Repeat caller tracking and metrics
- **Scheduled Reports** - Automated daily/weekly/monthly report generation
- **Admin Settings** - Configuration, thresholds, user management
- **Metrics Audit** - Data verification and quality checks

### Key Metrics

- Call Volume (Offered, Answered, Abandoned)
- Service Level % (configurable threshold, default 30s)
- Answer Rate & Abandon Rate
- Average Speed of Answer (ASA)
- Average Handle Time (AHT)
- Mean Opinion Score (MOS) with P10 percentile
- Bad Call Rate (MOS < threshold)
- Post Dial Delay (PDD)
- Callback metrics
- Repeat Caller Rate & metrics
- Codec distribution
- Hangup cause analysis

## Requirements

### Development (Windows)

- Docker Desktop for Windows
- Docker Compose (included with Docker Desktop)
- 8GB+ RAM recommended

### Production (Ubuntu)

- Docker and Docker Compose
- 16GB+ RAM recommended
- Ubuntu 20.04 LTS or later
- TLS certificates (Let's Encrypt recommended)

## Quick Start

### 1. Clone and Setup

```bash
git clone <repository>
cd phonereports
cp .env.example .env
```

### 2. Configure FusionPBX Connection

Edit `.env` and set:

```bash
FUSIONPBX_HOST=https://your-pbx.example.com
FUSIONPBX_API_KEY=your_api_key_here
```

### 3. Run on Windows (Development)

```bash
docker compose down --remove-orphans
docker compose up -d --build
```

Services will be available at:

- Frontend: <http://localhost:3000>
- Backend API: <http://localhost:8000>
- API Docs: <http://localhost:8000/docs>

### 4. Run on Ubuntu (Production)

```bash
# Set production environment
export ENVIRONMENT=production

# Update TLS certificates in docker/ssl/
# For Let's Encrypt:
# sudo certbot certonly --standalone -d your-domain.com

# Start services
docker compose down --remove-orphans
docker compose up -d --build

# View logs
docker compose logs -f
```

For routine production updates after the initial setup:

```bash
chmod +x scripts/update-production.sh
./scripts/update-production.sh
```

That script pulls the latest code from the current branch, rebuilds the app containers, and injects the current Git commit SHA into the Quality & Health page.

### 5. Authentication and Seeded Users

On backend startup, the container runs migrations, seeds users, and performs initial metadata sync (queues, agents, extensions):

```bash
python -m alembic upgrade head && python -m scripts.seed && python -m scripts.sync_metadata_only && python -m scripts.sync_extensions
```

Configure login users in `.env`:

```env
ADMIN_USERNAME=admin
ADMIN_PASSWORD=replace_with_strong_password
ADMIN_EMAIL=admin@example.com

# Optional additional users
# Format: username:password[:role[:email]];username2:password2[:role[:email]]
EXTRA_SEED_USERS=user1:asfg087ti23S:user:user1@local;user2:4q5AG8L4V5YT8:user:user2@local
```

Notes:

- `scripts.seed` is idempotent (existing users are not duplicated)
- Metadata sync scripts are run in non-blocking mode at container startup (app still boots if FusionPBX is temporarily unreachable)
- Default login is whatever `ADMIN_USERNAME` / `ADMIN_PASSWORD` are set to in `.env`

## Testing

Run backend unit tests quickly in your local environment:

```bash
pytest backend/tests -q
```

Run backend tests in Linux containers with Postgres and Redis (recommended before deploy):

```bash
docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from backend-tests
docker compose -f docker-compose.test.yml down -v
```

For full details, see [docs/TESTING_ENVIRONMENT.md](docs/TESTING_ENVIRONMENT.md).

## Architecture

### Backend (FastAPI)

- REST API endpoints for all dashboards
- Real-time KPI calculation
- User authentication and role-based access
- Database schema and migrations (Alembic)

### Worker (Celery + Redis)

- ETL pipeline for CDR data ingestion
- Periodic metadata synchronization
- Aggregation computation (hourly/daily)
- Scheduled report generation

### Database (PostgreSQL)

- CDR records with full call history
- Queue and agent metadata
- Hourly and daily aggregates
- User management and configurations

### Frontend (React + TypeScript)

- Responsive dashboard UI with Tailwind CSS
- Interactive charts using Recharts
- Global filtering across all pages
- Call record drilldowns and CSV export

### Reverse Proxy (Nginx)

- SSL/TLS termination
- Request routing
- Gzip compression
- Security headers

## Configuration

### Environment Variables

```env
# FusionPBX
FUSIONPBX_HOST=https://pbx.example.com
FUSIONPBX_API_KEY=your_key

# Database
DB_USER=phonereports
DB_PASSWORD=secure_password
DB_NAME=phonereports

# Redis
REDIS_URL=redis://redis:6379/0

# JWT
JWT_SECRET=your_secret_key

# Login protection
AUTH_LOGIN_RATE_LIMIT_WINDOW_SECONDS=60
AUTH_LOGIN_RATE_LIMIT_MAX_ATTEMPTS=120
AUTH_LOGIN_LOCKOUT_THRESHOLD=5
AUTH_LOGIN_LOCKOUT_SECONDS=300

# Frontend
VITE_API_URL=http://localhost:8000

# Timezone
DEFAULT_TIMEZONE=America/Phoenix

# Logging
LOG_LEVEL=INFO
ENVIRONMENT=development
```

### Calculations & Toggle Reference

For a full human-readable explanation of every metric formula and every filter toggle, see **[docs/CALCULATIONS.docx](docs/CALCULATIONS.docx)**.
The document covers queue deduplication logic, standard vs. strict answered mode, ASA/AHT derivation, agent attribution, abandoned classification, and all filter toggle behaviors.

### KPI Definitions

KPI calculations are defined in [backend/app/kpi_definitions.py](backend/app/kpi_definitions.py) as a single source of truth used across ETL and API:

- **Call Classifications** - Logic for offered, answered, abandoned, callback
- **Volume Metrics** - Inbound, queue-offered, answered, abandoned counts
- **Service Level** - Answer rate, abandon rate, ASA, wait times, service level %
- **Handle Time** - AHT with P90 percentile
- **Quality** - MOS avg/P10, bad call rate, codec distribution
- **Failures** - Hangup causes, Q850 codes, SIP disposition
- **Callbacks** - Offered, answered, completion rate
- **Repeat Callers** - Rate and repeat-after-abandon metrics

## Data Flow

### ETL Pipeline (Worker Tasks)

1. **CDR Ingestion** (every 5 minutes)
   - Fetch new CDRs from `/app/api/7/xml_cdr`
   - Upsert by `xml_cdr_uuid` (idempotent)
   - Maintain watermark for incremental updates
   - Include 15-minute safety window for late inserts

2. **Metadata Sync** (hourly)
   - Fetch queues, agents, tiers, extensions
   - Update human-friendly names
   - Maintain queue↔agent mappings

3. **Aggregation** (every 15 min / daily)
   - Compute hourly KPIs per queue
   - Compute daily KPIs per queue/agent
   - Build trend data for dashboards

4. **Report Generation** (scheduled)
   - Daily operations summary
   - Weekly performance pack
   - Monthly leadership summary
   - SLA compliance report

### API Endpoints (Examples)

```rest
GET /api/v1/dashboard/executive-overview?date_range=last_7&queues=q1,q2
GET /api/v1/dashboard/queue-performance/{queue_id}
GET /api/v1/dashboard/agent-performance/{agent_uuid}
GET /api/v1/cdr/calls?filters...
GET /api/v1/admin/metrics-audit
```

## Security

### Authentication

- JWT token-based authentication
- Role-based access control (Admin, Manager, User, Viewer)

### Number Masking

- Admins see unmasked caller numbers
- Managers and Users see masked numbers by default
- Configurable per role in Admin Settings

### Data Protection

- Passwords hashed with bcrypt
- Secrets stored in environment variables
- SSL/TLS encryption in transit
- Database connection pooling

## Performance Tuning

### Database Indexes

- CDR queries indexed on: `start_epoch`, `cc_queue`, `caller_id_number`
- Aggregates indexed on: `hour`, `date`, `queue_id`

### Caching Strategy

- Hourly aggregates cached for 1 hour
- Daily aggregates cached for 24 hours
- Queue/agent metadata cached with TTL refresh

### Query Optimization

- Aggregates pre-computed for dashboards
- Paginated call list queries
- Efficient date range filtering

## Monitoring & Logs

```bash
# View all logs
docker compose logs -f

# Backend logs only
docker compose logs -f backend

# Worker logs only
docker compose logs -f worker

# Database logs only
docker compose logs -f db
```

## Maintenance

### Database Backups

```bash
# Backup
docker compose exec db pg_dump -U phonereports phonereports > backup.sql

# Restore
docker compose exec -T db psql -U phonereports phonereports < backup.sql
```

### Restart Services

```bash
docker compose restart backend
docker compose restart worker
docker compose restart db
```

### View Database

```bash
docker compose exec db psql -U phonereports -d phonereports
```

## Troubleshooting

### Cannot connect to FusionPBX

- Verify `FUSIONPBX_HOST` and `FUSIONPBX_API_KEY` in `.env`
- Check network connectivity: `docker compose exec backend curl {FUSIONPBX_HOST}/health`
- Check API key permissions

### No data appearing

- Verify CDR records exist in FusionPBX
- Check worker logs: `docker compose logs -f worker`
- Manually trigger ETL: `docker compose exec worker celery -A app.celery_app call app.tasks.ingest_cdr_records`

### High memory usage

- Reduce worker concurrency in docker-compose.yml
- Check for large result sets in queries
- Review database connection pool settings

## Deployment Checklist

- [ ] Configure FUSIONPBX_HOST and API key
- [ ] Set strong DB and JWT secrets
- [ ] Configure SSL certificates
- [ ] Set ENVIRONMENT=production
- [ ] Review and adjust service resource limits
- [ ] Configure monitoring/alerting
- [ ] Set up log rotation
- [ ] Test backup/restore procedures
- [ ] Document custom queue names and mappings
- [ ] Set `ADMIN_USERNAME`, `ADMIN_PASSWORD`, and optional `EXTRA_SEED_USERS` in `.env`

## API Documentation

Swagger UI automatically generated: `http://localhost:8000/docs`

## Development

### Adding a New Dashboard

1. Create page component in `frontend/src/pages/`
2. Add API endpoint in `backend/app/api/`
3. Implement services in `backend/app/services/`
4. Update route in `frontend/src/App.tsx`

### Adding a New KPI

1. Define in `backend/app/kpi_definitions.py`
2. Implement calculation in aggregation task
3. Add to API response schema
4. Add widget to dashboard UI

## Documentation Update Policy

To keep markdown documentation current as code is merged:

- Pull requests that modify non-markdown files must also include at least one `.md` update.
- Markdown files are linted in CI to keep style consistent with the existing docs in this repository.
- Update the most relevant document(s), typically `README.md` and/or files in `docs/`.

### Database Migrations

```bash
# Create migration
docker compose exec backend alembic revision --autogenerate -m "description"

# Apply migrations
docker compose exec backend alembic upgrade head
```

## Support & Issues

For issues, please check:

1. Logs: `docker compose logs -f`
2. FusionPBX API connectivity
3. Database connection status
4. Redis connectivity for background tasks

## License

[Your License Here]

## Authors

Built for FusionPBX Call Center Analytics
