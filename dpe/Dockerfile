FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y postgresql-client libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dpe_pilot/ ./dpe_pilot/

ENV PYTHONUNBUFFERED=1

CMD ["uvicorn", "dpe_pilot.main:app", "--host", "0.0.0.0", "--port", "8000"]
