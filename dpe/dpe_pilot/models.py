from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry
import uuid
from datetime import datetime

Base = declarative_base()


class RatingsMetadata(Base):
    __tablename__ = "ratings_metadata"

    id = Column(Integer, primary_key=True)
    rating_code = Column(String(1), unique=True, nullable=False)  # A-G
    label = Column(String(50), nullable=False)  # "Very Efficient", "Efficient", etc.
    color_hex = Column(String(7), nullable=False)  # #00AA00, #FF0000, etc.
    min_consumption = Column(Float, nullable=True)  # kWh/m²/year
    max_consumption = Column(Float, nullable=True)


class Building(Base):
    __tablename__ = "buildings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    address = Column(String(255), nullable=False)
    city = Column(String(100), nullable=True)
    postal_code = Column(String(5), nullable=True)
    location = Column(Geometry("POINT", srid=4326), nullable=False)  # lat/lon for geospatial queries
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    dpe_rating = Column(String(1), ForeignKey("ratings_metadata.rating_code"), nullable=False)  # A-G
    consumption_kwh = Column(Float, nullable=True)  # Annual consumption in kWh
    renovation_recommendations = Column(Text, nullable=True)  # JSON-serialized recommendations
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    source_id = Column(String(100), unique=True, nullable=True)  # data.gouv dataset ID

    __table_args__ = (
        # Geospatial index for fast distance queries
        # CREATE INDEX ON buildings USING GIST (location);
    )
