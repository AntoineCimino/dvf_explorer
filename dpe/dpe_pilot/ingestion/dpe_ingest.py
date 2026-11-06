import requests
import csv
import io
import json
import logging
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from geoalchemy2.elements import WKTElement
from ..models import Building, RatingsMetadata
from ..config import settings

logger = logging.getLogger(__name__)

RATINGS = {
    "A": {"label": "Very Efficient", "color": "#00AA00", "min": 0, "max": 100},
    "B": {"label": "Efficient", "color": "#55DD00", "min": 100, "max": 150},
    "C": {"label": "Good", "color": "#FFFF00", "min": 150, "max": 250},
    "D": {"label": "Average", "color": "#FF8800", "min": 250, "max": 330},
    "E": {"label": "Weak", "color": "#FF4400", "min": 330, "max": 420},
    "F": {"label": "Very Weak", "color": "#FF0000", "min": 420, "max": 500},
    "G": {"label": "Extremely Weak", "color": "#AA0000", "min": 500, "max": 99999},
}


def init_ratings(db: Session) -> int:
    """Initialize ratings_metadata table. Returns count of created ratings."""
    count = 0
    for code, info in RATINGS.items():
        existing = db.query(RatingsMetadata).filter_by(rating_code=code).first()
        if not existing:
            db.add(
                RatingsMetadata(
                    rating_code=code,
                    label=info["label"],
                    color_hex=info["color"],
                    min_consumption=info["min"],
                    max_consumption=info["max"],
                )
            )
            count += 1
    db.commit()
    return count


def ingest_dpe_sample_data(db: Session, num_records: int = 1000) -> dict:
    """
    Ingest sample DPE data for testing/demo.
    Returns: {"inserted": N, "skipped": N, "errors": N}
    """
    import random

    cities = ["Paris", "Lyon", "Marseille", "Toulouse", "Nice", "Nantes", "Strasbourg", "Bordeaux"]
    postal_codes = {"Paris": "75000", "Lyon": "69000", "Marseille": "13000", "Toulouse": "31000",
                    "Nice": "06000", "Nantes": "44000", "Strasbourg": "67000", "Bordeaux": "33000"}
    ratings = list(RATINGS.keys())
    stats = {"inserted": 0, "skipped": 0, "errors": 0}

    for i in range(num_records):
        try:
            city = random.choice(cities)
            postal = postal_codes.get(city, "00000")

            # Geographic spread across France
            lat_center, lon_center = (48.8, 2.3) if city == "Paris" else (45.0, 4.8)
            lat = lat_center + random.uniform(-2.0, 2.0)
            lon = lon_center + random.uniform(-2.0, 2.0)

            rating = random.choice(ratings)
            consumption = RATINGS[rating]["min"] + random.uniform(0, 50)

            point = WKTElement(f"POINT({lon} {lat})", extended=True)
            source_id = f"sample_{i:06d}"

            # Skip if already exists
            if db.query(Building).filter_by(source_id=source_id).first():
                stats["skipped"] += 1
                continue

            building = Building(
                address=f"{i} Rue Sample, {postal} {city}",
                city=city,
                postal_code=postal,
                location=point,
                lat=lat,
                lon=lon,
                dpe_rating=rating,
                consumption_kwh=consumption,
                renovation_recommendations=json.dumps([
                    {"type": "insulation", "cost": 5000, "savings": "20%"},
                    {"type": "heating", "cost": 8000, "savings": "30%"}
                ]),
                source_id=source_id,
            )
            db.add(building)
            stats["inserted"] += 1

            # Batch commit every 100 records
            if stats["inserted"] % 100 == 0:
                db.commit()

        except Exception as e:
            logger.error(f"Error ingesting record {i}: {e}")
            stats["errors"] += 1
            db.rollback()

    db.commit()
    return stats


def ingest_from_data_gouv(db: Session, dataset_url: str = None) -> dict:
    """
    Fetch real DPE data from data.gouv API.
    For now, falls back to sample data.
    """
    logger.info("📥 Fetching DPE data from data.gouv...")

    # TODO: Implement actual data.gouv API fetch
    # Example dataset: https://www.data.gouv.fr/datasets/dpe-logements-existants-depuis-juillet-2021

    # For MVP, use sample data
    return ingest_dpe_sample_data(db, num_records=1000)


if __name__ == "__main__":
    import sys
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from ..models import Base

    logging.basicConfig(level=logging.INFO)

    engine = create_engine(settings.database_url, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Create tables
        Base.metadata.create_all(bind=engine)
        logger.info("✅ Tables created")

        # Initialize ratings
        ratings_count = init_ratings(db)
        logger.info(f"✅ Initialized {ratings_count} ratings")

        # Ingest data
        stats = ingest_from_data_gouv(db)
        logger.info(f"✅ Ingestion complete: {stats['inserted']} inserted, {stats['skipped']} skipped, {stats['errors']} errors")

    except Exception as e:
        logger.error(f"❌ Ingestion failed: {e}")
        sys.exit(1)
    finally:
        db.close()
