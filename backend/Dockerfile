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


##
# Frontend render-script dependencies.
# - `send_report_run` (backend/tasks/report_tasks.py) shells out to
#   `npx tsx frontend/emails/render-report.ts` to render the newsletter
#   HTML/text via React Email. That script lives in the frontend/ package
#   and needs its node_modules (@react-email/*, react, react-dom, tsx, ...)
#   resolvable at runtime.
# - This stage runs `pnpm install` against the frontend workspace so the
#   resulting node_modules can be baked into the runner image below,
#   independent of whatever's on the host.
# - This backend Dockerfile's primary build context stays `./backend`
#   (unchanged, so existing Railway/CI/compose configs that build with
#   context=./backend keep working). frontend/ is supplied as a separate
#   *named* BuildKit context called "frontend" -- see the `additional_contexts`
#   entries in docker-compose.yml / deploy/compose/docker-compose.local.yml
#   and the `build-contexts` input in .github/workflows/docker-build.yml.
#   Any build invocation that does NOT pass that named context (e.g. a bare
#   `docker build ./backend` or an unmodified Railway service) will fail this
#   stage -- see final-review-fix-report.md for what's covered vs. not.
##
FROM node:20-bookworm-slim AS frontend-deps

WORKDIR /frontend

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

COPY --from=frontend package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY --from=frontend xlsx-0.20.3.tgz ./xlsx-0.20.3.tgz

RUN pnpm install --frozen-lockfile


FROM python:3.11-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV PATH="/opt/venv/bin:$PATH"
ENV PROCESS_TYPE=api
# Sibling directory the render subprocess uses to find render-report.ts and
# its node_modules. Locally (outside Docker) report_tasks.py computes this
# from __file__ since backend/ and frontend/ are checkout siblings; inside
# the container we bake/copy frontend's render assets to this fixed path
# and point the task at it explicitly.
ENV FRONTEND_EMAILS_DIR=/frontend/emails

# Runtime deps: libpq for Postgres connectivity, Node.js/npm for the
# render-report.ts subprocess invoked by tasks/report_tasks.py.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    nodejs \
    npm \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY . .

# Render script + its dependencies (see frontend-deps stage above). Only
# frontend/emails/** is needed at runtime -- render-report.ts and everything
# it imports (report-newsletter.tsx + emails/components/*) is self-contained
# there and only reaches into @react-email/components from node_modules.
COPY --from=frontend-deps /frontend/node_modules /frontend/node_modules
COPY --from=frontend emails /frontend/emails
COPY --from=frontend tsconfig.json package.json /frontend/

# Non-root user for production hardening
RUN useradd --create-home --uid 10001 app \
  && chown -R app:app /app /frontend
USER app

EXPOSE 8000

# Use PROCESS_TYPE to run API, MCP, Celery worker, or Celery beat from the same image.
CMD ["sh", "-c", "if [ \"$PROCESS_TYPE\" = \"worker\" ]; then exec celery -A celery_app worker --loglevel=info --concurrency=4; elif [ \"$PROCESS_TYPE\" = \"beat\" ]; then exec celery -A celery_app beat --loglevel=info; elif [ \"$PROCESS_TYPE\" = \"mcp\" ]; then exec uvicorn mcp_server:app --host 0.0.0.0 --port ${PORT:-8001}; else exec gunicorn -k uvicorn.workers.UvicornWorker app.main:app --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120; fi"]
