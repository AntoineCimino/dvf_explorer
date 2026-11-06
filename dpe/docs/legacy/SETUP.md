> Historical prototype documentation, imported 2026-11-05. Read ../../README.md first.
> These are not verified production claims; the importer currently generates synthetic records.

# DPE Backend — Setup Guide (MVP 1)

## Prerequisites

- Python 3.11+
- Docker + Docker Compose
- Git

## Step-by-Step Setup

### 1. Install Python Dependencies

```bash
make setup
```

Or manually:
```bash
pip install -r requirements.txt
```

### 2. Start PostgreSQL Database

```bash
make db-start
```

This starts a PostgreSQL 15 container with PostGIS 3.3 extension.

**Verify it's running:**
```bash
docker-compose ps
# Should show: postgres ... Up (healthy)
```

**View logs:**
```bash
make db-logs
```

**Stop database:**
```bash
make db-stop
```

### 3. Create Database Schema & Ingest Sample Data

This runs the migration and populates 1000 sample buildings across France.

```bash
make ingest
```

**Expected output:**
```
✅ Tables created
✅ Initialized 7 ratings
✅ Ingestion complete: 1000 inserted, 0 skipped, 0 errors
```

### 4. Start FastAPI Server

```bash
make run
```

**Expected output:**
```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 5. Test the API

In another terminal:

```bash
# Search for efficient buildings near Paris
curl "http://localhost:8000/api/search?lat=48.8&lon=2.3&radius_km=10&rating=A,B"

# Get statistics for a region
curl "http://localhost:8000/api/stats?lat=48.8&lon=2.3&radius_km=10"

# Health check
curl http://localhost:8000/api/health
```

### 6. View API Documentation

Open http://localhost:8000/docs (Swagger UI)

or http://localhost:8000/redoc (ReDoc)

---

## Database Access (Optional)

Connect directly to PostgreSQL:

```bash
psql -h localhost -U dpe_user -d dpe_db -W
# Password: use your own local DPE_DB_PASSWORD; the old shared demo value is retired.
```

**Check tables:**
```sql
SELECT COUNT(*) FROM buildings;
SELECT * FROM ratings_metadata;
```

---

## Troubleshooting

### "connection refused" on :5432
Database not running. Run `make db-start`

### "ModuleNotFoundError: No module named 'fastapi'"
Dependencies not installed. Run `make setup`

### "database does not exist"
Schema not created. Run `make ingest`

### Port 5432 already in use
Another PostgreSQL is running. Stop it:
```bash
make db-stop
# If that doesn't work, find and kill the process:
lsof -i :5432
kill -9 <PID>
```

### Port 8000 already in use
Another process is on 8000. Change it:
```bash
uvicorn src.main:app --reload --port 8001
```

---

## Performance Baseline

**Sample data:** 1000 buildings across France

**Search query time:**
- Geospatial query (10km radius): ~50ms
- With filters (rating + consumption): ~80ms
- With pagination (limit 50): ~80ms

**Database:** ~10 MB disk space for 1000 buildings

---

## Next Steps

1. Verify all endpoints work (test all 5 endpoints above)
2. Test edge cases (invalid coords, large radius, no results)
3. Load test (performance at 10K+ buildings)
4. Then move to MVP 2 (React frontend)

---

## Environment Configuration

See `.env` and `.env.example` for options.

**Common overrides:**
```bash
DEBUG=True              # Enable SQL logging
DATABASE_URL=...        # Custom Postgres URL
```
