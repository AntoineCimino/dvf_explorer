import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Use in-memory SQLite for testing (without PostGIS for now)
TEST_DB_URL = "sqlite:///:memory:"

# For now, skip PostGIS-dependent tests
# In CI/CD, use a real PostgreSQL with PostGIS


def test_health():
    """Test that the API is running."""
    from dpe_pilot.main import app

    client = TestClient(app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.skip(reason="Requires PostgreSQL + PostGIS")
def test_search_endpoint():
    """Test the search endpoint."""
    pass


@pytest.mark.skip(reason="Requires PostgreSQL + PostGIS")
def test_stats_endpoint():
    """Test the stats endpoint."""
    pass
