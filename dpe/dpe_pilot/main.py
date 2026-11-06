import logging
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, func, and_
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import OperationalError
from geoalchemy2.functions import ST_DWithin, ST_AsText
from geoalchemy2 import Geometry
from contextlib import contextmanager

from .config import settings
from .models import Base, Building, RatingsMetadata
from .schemas import SearchParams, SearchResponse, BuildingResponse, StatsResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.api_title, version=settings.api_version)

engine = create_engine(settings.database_url, echo=settings.debug)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.on_event("startup")
def startup():
    # Enable PostGIS
    with engine.begin() as conn:
        conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS postgis")
    # Create tables
    Base.metadata.create_all(bind=engine)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/search", response_model=SearchResponse)
async def search(
    params: SearchParams = Depends(),
    db: Session = Depends(get_db),
):
    """
    Search buildings by location and filters.
    """
    try:
        from geoalchemy2.elements import WKTElement

        # Validate coordinates
        if not (-90 <= params.lat <= 90 and -180 <= params.lon <= 180):
            raise HTTPException(status_code=400, detail="Invalid coordinates (lat: -90 to 90, lon: -180 to 180)")

        if params.radius_km <= 0 or params.radius_km > 100:
            raise HTTPException(status_code=400, detail="Radius must be > 0 and <= 100 km")

        point = WKTElement(f"POINT({params.lon} {params.lat})", extended=True)

        query = db.query(Building).filter(
            ST_DWithin(Building.location, point, params.radius_km * 1000)  # Convert km to meters
        )

        if params.rating:
            ratings = [r.strip().upper() for r in params.rating.split(",") if r.strip()]
            valid_ratings = {"A", "B", "C", "D", "E", "F", "G"}
            if not all(r in valid_ratings for r in ratings):
                raise HTTPException(status_code=400, detail=f"Invalid ratings. Must be A-G.")
            query = query.filter(Building.dpe_rating.in_(ratings))

        if params.consumption_max and params.consumption_max > 0:
            query = query.filter(Building.consumption_kwh <= params.consumption_max)

        total_count = query.count()
        buildings = query.offset(params.offset).limit(params.limit).all()

        logger.info(f"Search: lat={params.lat}, lon={params.lon}, radius={params.radius_km}km, results={total_count}")

        return SearchResponse(
            total_count=total_count,
            limit=params.limit,
            offset=params.offset,
            buildings=[BuildingResponse.model_validate(b) for b in buildings],
        )

    except OperationalError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=503, detail="Database connection error")
    except Exception as e:
        logger.error(f"Unexpected error in search: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/api/stats", response_model=StatsResponse)
async def stats(
    lat: float,
    lon: float,
    radius_km: float = 10.0,
    db: Session = Depends(get_db),
):
    """
    Get aggregated statistics for buildings in a region.
    """
    try:
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise HTTPException(status_code=400, detail="Invalid coordinates")

        from geoalchemy2.elements import WKTElement

        point = WKTElement(f"POINT({lon} {lat})", extended=True)

        buildings = db.query(Building).filter(
            ST_DWithin(Building.location, point, radius_km * 1000)
        ).all()

        rating_dist = {}
        for b in buildings:
            rating_dist[b.dpe_rating] = rating_dist.get(b.dpe_rating, 0) + 1

        consumptions = [b.consumption_kwh for b in buildings if b.consumption_kwh]
        avg_consumption = sum(consumptions) / len(consumptions) if consumptions else None

        logger.info(f"Stats: region lat={lat}, lon={lon}, buildings={len(buildings)}")

        return StatsResponse(
            total_buildings=len(buildings),
            rating_distribution=rating_dist,
            avg_consumption=avg_consumption,
            avg_recommendations_count=sum([1 for b in buildings if b.renovation_recommendations]),
        )

    except OperationalError as e:
        logger.error(f"Database error: {e}")
        raise HTTPException(status_code=503, detail="Database connection error")
    except Exception as e:
        logger.error(f"Unexpected error in stats: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
