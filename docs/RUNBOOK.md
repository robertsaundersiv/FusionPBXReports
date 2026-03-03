# Development Runbook

## Initial Setup (First Time)

### Prerequisites
- Docker Desktop (Windows) or Docker + Docker Compose (Ubuntu)
- Git
- Text editor or IDE

### Step 1: Clone Repository

```bash
git clone <repository-url>
cd phonereports
```

### Step 2: Create Environment File

```bash
cp .env.example .env
```

Edit `.env` with your FusionPBX details:

```bash
# Required
FUSIONPBX_HOST=https://your-pbx.example.com
FUSIONPBX_API_KEY=your_api_key_here

# Optional but recommended
DB_PASSWORD=YourSecurePassword123!
JWT_SECRET=YourJWTSecret123456789!
ADMIN_PASSWORD=AdminPassword123!
```

### Step 3: Generate SSL Certificates (Development)

For development with self-signed certs:

```bash
cd docker/ssl
openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem -keyout key.pem -days 365
# Answer the prompts (can use defaults)
cd ../..
```

### Step 4: Start Services

Windows (PowerShell):
```powershell
docker-compose up -d
```

Ubuntu/Linux:
```bash
docker-compose up -d
```

### Step 5: Initialize Database

Wait for postgres to be healthy (~10 seconds), then:

```bash
docker-compose exec backend python -m scripts.init
docker-compose exec backend python -m scripts.seed
```

### Step 6: Access Application

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Nginx**: https://localhost (with TLS warning in dev)

### Step 7: Login

Default credentials (change in production):
- Username: `admin`
- Password: `changeme` (or what you set in ADMIN_PASSWORD)

---

## Common Development Tasks

### Viewing Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f backend
docker-compose logs -f worker
docker-compose logs -f postgres
```

### Database Access

```bash
# PostgreSQL CLI
docker-compose exec postgres psql -U phonereports -d phonereports

# Inside psql
\dt                    # List tables
SELECT * FROM users;   # Query users
```

### Rebuilding Services

```bash
# After changing code
docker-compose up --build -d

# Or rebuild specific service
docker-compose build backend
docker-compose up -d backend
```

### Fresh Start

```bash
# Stop and remove everything
docker-compose down

# Remove volumes (clear database)
docker-compose down -v

# Restart clean
docker-compose up -d
```

### Run ETL Tasks Manually

```bash
# Ingest CDRs
docker-compose exec worker celery -A app.celery_app call app.tasks.ingest_cdr_records

# Sync metadata
docker-compose exec worker celery -A app.celery_app call app.tasks.sync_queue_metadata

# Compute aggregates
docker-compose exec worker celery -A app.celery_app call app.tasks.compute_hourly_aggregates
```

### Database Backup/Restore

```bash
# Backup
docker-compose exec postgres pg_dump -U phonereports phonereports > backup.sql

# Restore
docker-compose exec -T postgres psql -U phonereports phonereports < backup.sql
```

### Frontend Development

```bash
# Hot reload automatically active in development
# Edit files in frontend/src/ and changes appear instantly

# Build for production
docker-compose exec frontend npm run build
```

### Backend Development

```bash
# Hot reload automatically active
# Edit files in backend/app/ and FastAPI auto-reloads

# Run tests
docker-compose exec backend pytest

# Format code
docker-compose exec backend black app/
docker-compose exec backend isort app/
```

---

## Testing

### Run Backend Tests

```bash
docker-compose exec backend pytest
```

### Test FusionPBX Connectivity

```bash
docker-compose exec backend python -c "
import asyncio
from app.clients.fusionpbx import get_fusion_client

async def test():
    client = get_fusion_client()
    await client.initialize()
    queues = await client.get_call_center_queues()
    print(f'Found {len(queues)} queues')
    await client.close()

asyncio.run(test())
"
```

### Check Database Connection

```bash
docker-compose exec backend python -c "
from app.database import SessionLocal
db = SessionLocal()
result = db.query('SELECT 1').scalar()
print('Database connected')
"
```

---

## Troubleshooting

### Services Won't Start

```bash
# Check logs
docker-compose logs

# Verify compose file
docker-compose config

# Rebuild everything
docker-compose down -v
docker-compose up --build -d
```

### Database Connection Error

```bash
# Wait for postgres to be ready
docker-compose logs postgres | grep "ready to accept"

# Or restart postgres
docker-compose restart postgres
docker-compose up -d backend worker
```

### Port Already in Use

```bash
# Find what's using port 8000
lsof -i :8000  # Unix/Linux/Mac
netstat -ano | findstr :8000  # Windows

# Or change ports in docker-compose.yml
# Then: docker-compose up -d
```

### Out of Memory

```bash
# Reduce worker concurrency in docker-compose.yml
# Change: --concurrency=2 to --concurrency=1

# Restart
docker-compose restart worker
```

### FusionPBX API Connection Issues

```bash
# Test connectivity
docker-compose exec backend curl https://<your-pbx>/app/api/7/xml_cdr

# Check credentials
echo $FUSIONPBX_HOST
echo $FUSIONPBX_API_KEY

# Verify in .env file
cat .env | grep FUSIONPBX
```

---

## Performance Tuning (Development)

### Enable Query Logging

```bash
# In .env
SQL_ECHO=true

# Restart backend
docker-compose restart backend
```

### Monitor Resource Usage

```bash
# Windows PowerShell
docker stats

# Linux/Mac
docker stats
```

### Profile Slow Queries

```bash
docker-compose exec postgres pg_stat_statements extension
# Then: SELECT * FROM pg_stat_statements WHERE mean_time > 1000;
```

---

## Code Organization

```
backend/
├── app/
│   ├── __init__.py          # Package init
│   ├── main.py              # FastAPI app
│   ├── auth.py              # Authentication
│   ├── database.py          # DB connection
│   ├── kpi_definitions.py   # Single source of truth
│   ├── api/                 # API routes
│   │   ├── auth.py
│   │   ├── cdr.py
│   │   ├── dashboard.py
│   │   └── admin.py
│   ├── clients/             # External integrations
│   │   └── fusionpbx.py    # FusionPBX client
│   ├── models/              # SQLAlchemy models
│   ├── schemas/             # Pydantic schemas
│   └── services/            # Business logic
├── migrations/              # Alembic migrations
├── scripts/                 # Utility scripts
│   ├── init.py
│   └── seed.py
└── requirements.txt         # Python dependencies
```

---

## Git Workflow

```bash
# Create feature branch
git checkout -b feature/new-dashboard

# Make changes
# ... edit files ...

# Commit
git add .
git commit -m "Add new dashboard feature"

# Push
git push origin feature/new-dashboard

# Create pull request
# ... on GitHub/GitLab ...
```

---

## Documentation

- **KPI Definitions**: See [KPI_DEFINITIONS.md](KPI_DEFINITIONS.md)
- **Architecture**: See [ARCHITECTURE.md](ARCHITECTURE.md)
- **API Docs**: http://localhost:8000/docs (Swagger UI)
- **Comments**: Most complex logic has inline comments

---

## Quick Reference

| Task | Command |
|------|---------|
| Start all services | `docker-compose up -d` |
| Stop all services | `docker-compose down` |
| View logs | `docker-compose logs -f [service]` |
| Access database | `docker-compose exec postgres psql -U phonereports` |
| Run migrations | `docker-compose exec backend alembic upgrade head` |
| Rebuild service | `docker-compose build [service]` |
| Execute backend command | `docker-compose exec backend [command]` |
| Execute worker command | `docker-compose exec worker [command]` |

---

## When Something Goes Wrong

1. **Check logs first**: `docker-compose logs -f`
2. **Verify environment**: `cat .env | grep -v ^#`
3. **Test dependencies**: Check FusionPBX connectivity, database, Redis
4. **Clear and restart**: `docker-compose down -v && docker-compose up -d`
5. **Check disk space**: `docker system df`
6. **Ask for help**: Include logs and `.env` (with secrets removed)
