FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# Cloud Run sets $PORT; uvicorn must bind to it, not a hardcoded port.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
