> Historical prototype documentation, imported 2026-11-05. Read ../../README.md first.
> These are not verified production claims; the importer currently generates synthetic records.

# DPE Backend — Data Web Framework Pilot

Building Energy Performance (DPE) search API: reusable vertical SaaS template for data-driven applications.

## Quick Start

### 1. Setup

```bash
make setup
```

### 2. Start Database (PostgreSQL + PostGIS)

```bash
make db-start
```

Wait for health check (~5s):
```bash
docker-compose logs postgres
# Should see: "database system is ready to accept connections"
```

### 3. Ingest Sample Data (1000 buildings)

```bash
make ingest
```

### 4. Run API Server

```bash
make run
```

API available at http://localhost:8000

## API Endpoints

### Search Buildings

```bash
curl "http://localhost:8000/api/search?lat=48.8&lon=2.3&radius_km=10&rating=A,B,C&limit=20"
```

**Parameters:**
- `lat`, `lon`: Search center (WGS84)
- `radius_km`: Search radius (default: 10)
- `rating`: Filter by DPE rating (A-G, comma-separated)
- `consumption_max`: Max annual consumption (kWh, optional)
- `limit`, `offset`: Pagination

**Response:**
```json
{
  "total_count": 42,
  "limit": 20,
  "offset": 0,
  "buildings": [
    {
      "id": "uuid",
      "address": "123 Rue Sample",
      "city": "Paris",
      "postal_code": "75000",
      "lat": 48.8,
      "lon": 2.3,
      "dpe_rating": "A",
      "consumption_kwh": 85.5,
      "renovation_recommendations": "[...]",
      "updated_at": "2026-06-29T..."
    }
  ]
}
```

### Aggregated Stats

```bash
curl "http://localhost:8000/api/stats?lat=48.8&lon=2.3&radius_km=10"
```

**Response:**
```json
{
  "total_buildings": 42,
  "rating_distribution": {"A": 10, "B": 12, "C": 20, ...},
  "avg_consumption": 120.5,
  "avg_recommendations_count": 2
}
```

### Health Check

```bash
curl http://localhost:8000/api/health
```

## Development

### Run Tests

```bash
make test
```

### View Database Logs

```bash
make db-logs
```

### Stop Database

```bash
make db-stop
```

## Database Schema

### buildings (main table)
- `id` (UUID, PK)
- `address`, `city`, `postal_code`
- `location` (PostGIS POINT, indexed for geospatial queries)
- `lat`, `lon` (for API responses)
- `dpe_rating` (A-G, FK to ratings_metadata)
- `consumption_kwh` (annual energy consumption)
- `renovation_recommendations` (JSON array)
- `updated_at` (timestamp)
- `source_id` (unique, for tracking data source)

### ratings_metadata (lookup table)
- `id` (PK)
- `rating_code` (A-G)
- `label` (e.g., "Very Efficient")
- `color_hex` (UI color)
- `min_consumption`, `max_consumption`

## Architecture Notes

- **Framework:** FastAPI (async, Pydantic validation)
- **ORM:** SQLAlchemy 2.0
- **Database:** PostgreSQL 15 + PostGIS 3.3 (geospatial)
- **Geospatial Queries:** `ST_DWithin` for radius search
- **Docker:** Containerized for production deployment

## Next Phases

- **MVP 2 (Week 3-4):** React frontend + Leaflet map + real-time filters
- **MVP 3 (Week 5):** UX polish + accessibility + CI/CD (GitHub Actions)

## Environment Variables

See `.env.example` for local development setup.
