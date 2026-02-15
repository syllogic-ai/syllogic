# syntax=docker/dockerfile:1.7

##
# Frontend (Next.js) production image.
# - Multi-stage build
# - Production deps in runtime image (reliable for DB + migrations)
# - Includes DB migrations runner + SQL migrations
##

FROM node:20-bookworm-slim AS deps
WORKDIR /app

# Install dependencies using pnpm (via Corepack).
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

# Only copy what we need to install deps (better layer caching).
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY xlsx-0.20.3.tgz ./xlsx-0.20.3.tgz

RUN pnpm install --frozen-lockfile


FROM deps AS prod-deps
# Drop devDependencies for the runtime image.
RUN pnpm prune --prod


FROM node:20-bookworm-slim AS builder
WORKDIR /app

ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Next build evaluates some server files at build time; provide safe defaults.
ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV DATABASE_URL="postgresql://postgres:postgres@localhost:5432/postgres"
ENV APP_URL="http://localhost:8080"
ENV BETTER_AUTH_URL="http://localhost:8080"
ENV BETTER_AUTH_SECRET="build-only-secret"

RUN pnpm build


FROM node:20-bookworm-slim AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Production dependencies + build output
COPY --from=prod-deps --chown=node:node /app/node_modules ./node_modules
COPY --from=builder --chown=node:node /app/package.json ./package.json
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder --chown=node:node /app/public ./public

# Migration runner + SQL migrations (used by docker-compose one-shot "migrate" service)
COPY --from=builder --chown=node:node /app/scripts/migrate.js ./scripts/migrate.js
COPY --from=builder --chown=node:node /app/lib/db/migrations ./lib/db/migrations

# Ensure uploads dir exists (can be mounted as a volume in production).
RUN mkdir -p /app/public/uploads && chown -R node:node /app/public/uploads

USER node

EXPOSE 3000
CMD ["node_modules/.bin/next", "start", "-p", "3000", "-H", "0.0.0.0"]
