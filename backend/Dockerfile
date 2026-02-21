# syntax=docker/dockerfile:1.7

##
# Backend (FastAPI + Celery) production image.
# - Multi-stage build (keep build deps out of runtime)
# - Non-root runtime user
##

FROM python:3.11-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Build deps (kept only in builder stage)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# Create venv so we can copy it into the runtime image
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
RUN pip install --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt


FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PATH="/opt/venv/bin:$PATH"
ENV PROCESS_TYPE=api

# Runtime deps (libpq for Postgres connectivity)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY . .

# Non-root user for production hardening
RUN useradd --create-home --uid 10001 app \
  && chown -R app:app /app
USER app

EXPOSE 8000

# Use PROCESS_TYPE to run API, Celery worker, or Celery beat from the same image.
CMD ["sh", "-c", "if [ \"$PROCESS_TYPE\" = \"worker\" ]; then exec celery -A celery_app worker --loglevel=info --concurrency=4; elif [ \"$PROCESS_TYPE\" = \"beat\" ]; then exec celery -A celery_app beat --loglevel=info; else exec gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120; fi"]
