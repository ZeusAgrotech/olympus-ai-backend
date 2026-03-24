FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if any needed (e.g. for psycopg2)
# libpq-dev is often needed for psycopg2
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run sets PORT (often 8080). Default matches local docker-compose.
EXPOSE 8080

ENV PYTHONPATH=/app
ENV ENVIRONMENT=production

# Shell form so ${PORT} expands at container start (Cloud Run injects PORT).
CMD exec gunicorn --bind "0.0.0.0:${PORT:-8080}" --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile - wsgi:app
