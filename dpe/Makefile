.PHONY: setup db-start db-stop ingest test run docker-build clean help

help:
	@echo "DPE Backend Development Commands:"
	@echo "  make setup              - Install Python dependencies"
	@echo "  make db-start           - Start PostgreSQL + PostGIS (Docker)"
	@echo "  make db-stop            - Stop PostgreSQL"
	@echo "  make ingest             - Ingest sample DPE data (requires running DB)"
	@echo "  make test               - Run tests"
	@echo "  make run                - Start FastAPI dev server (port 8000)"
	@echo "  make clean              - Clean __pycache__ and .pyc files"

setup:
	pip install -r requirements.txt

db-start:
	docker compose up -d postgres
	@echo "✅ PostgreSQL started on localhost:5432"

db-stop:
	docker compose down

db-logs:
	docker compose logs -f postgres

ingest:
	python -m dpe_pilot.ingestion.dpe_ingest

test:
	pytest tests/ -v

run:
	uvicorn dpe_pilot.main:app --reload --host 0.0.0.0 --port 8000

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
