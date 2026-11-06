from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class SearchParams(BaseModel):
    lat: float = Field(..., description="Latitude for search center")
    lon: float = Field(..., description="Longitude for search center")
    radius_km: float = Field(default=10.0, description="Search radius in kilometers")
    rating: Optional[str] = Field(None, description="Filter by rating(s): A,B,C,D,E,F,G (comma-separated)")
    consumption_max: Optional[float] = Field(None, description="Max annual consumption (kWh)")
    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class BuildingResponse(BaseModel):
    id: str
    address: str
    city: Optional[str]
    postal_code: Optional[str]
    lat: float
    lon: float
    dpe_rating: str
    consumption_kwh: Optional[float]
    renovation_recommendations: Optional[str]
    updated_at: datetime

    class Config:
        from_attributes = True


class SearchResponse(BaseModel):
    total_count: int
    limit: int
    offset: int
    buildings: List[BuildingResponse]


class StatsResponse(BaseModel):
    total_buildings: int
    rating_distribution: dict  # {"A": 100, "B": 200, ...}
    avg_consumption: Optional[float]
    avg_recommendations_count: int
