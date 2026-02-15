#!/usr/bin/env bash
set -euo pipefail

REPO="syllogic-ai/personal-finance-app"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Please run as root (e.g. sudo ./install.sh vX.Y.Z)"
  exit 1
fi

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "Usage: ./install.sh vX.Y.Z"
  echo "Example: ./install.sh v1.2.3"
  exit 1
fi

INSTALL_DIR="/opt/syllogic"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

echo "[install] Installing into: $INSTALL_DIR"

if ! command -v curl >/dev/null 2>&1; then
  echo "[install] curl not found. Installing..."
  apt-get update
  apt-get install -y curl
fi

if ! command -v openssl >/dev/null 2>&1; then
  echo "[install] openssl not found. Installing..."
  apt-get update
  apt-get install -y openssl
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "[install] Docker not found. Installing via get.docker.com..."
  curl -fsSL https://get.docker.com | sh
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "[install] docker compose plugin not found. Installing..."
  apt-get update
  apt-get install -y docker-compose-plugin
fi

mkdir -p "$INSTALL_DIR"

echo "[install] Downloading compose bundle for $VERSION..."
BUNDLE_URL="https://github.com/${REPO}/releases/download/${VERSION}/compose-bundle.tar.gz"
curl -fL "$BUNDLE_URL" -o "$TMP_DIR/compose-bundle.tar.gz"

echo "[install] Extracting bundle..."
tar -xzf "$TMP_DIR/compose-bundle.tar.gz" -C "$INSTALL_DIR"

POSTGRES_USER="financeuser"
POSTGRES_DB="finance_db"
POSTGRES_PASSWORD="$(openssl rand -hex 24)"
BETTER_AUTH_SECRET="$(openssl rand -hex 32)"

read -r -p "Domain (e.g. finance.example.com) or leave blank for HTTP-only: " DOMAIN || true
DOMAIN="${DOMAIN:-}"

APP_URL=""
CADDY_ADDRESS=""
ACME_EMAIL=""

if [[ -n "$DOMAIN" ]]; then
  read -r -p "ACME email (for Let's Encrypt): " ACME_EMAIL || true
  ACME_EMAIL="${ACME_EMAIL:-}"
  APP_URL="https://${DOMAIN}"
  CADDY_ADDRESS="${DOMAIN}"
else
  # HTTP-only mode (no TLS)
  APP_URL="http://localhost:8080"
  CADDY_ADDRESS=":80"
fi

cat > "$INSTALL_DIR/.env" <<EOF
APP_VERSION=${VERSION}
APP_URL=${APP_URL}
BETTER_AUTH_SECRET=${BETTER_AUTH_SECRET}
CADDY_ADDRESS=${CADDY_ADDRESS}
ACME_EMAIL=${ACME_EMAIL}
HTTP_PORT=8080
HTTPS_PORT=443
MCP_PORT=8001

POSTGRES_USER=${POSTGRES_USER}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DB=${POSTGRES_DB}
DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}

REDIS_URL=redis://redis:6379/0

BACKEND_URL=http://backend:8000
CORS_ALLOW_ORIGINS=${APP_URL}
API_DOCS_ENABLED=false

STORAGE_PROVIDER=local
LOCAL_STORAGE_PATH=uploads
EOF

echo "[install] Starting services..."
cd "$INSTALL_DIR"
docker compose --env-file .env -f docker-compose.yml pull
docker compose --env-file .env -f docker-compose.yml up -d

echo
echo "[install] Done."
echo "- Config: $INSTALL_DIR/.env"
echo "- Stack:  docker compose --env-file .env -f docker-compose.yml ps"
echo
if [[ -n "$DOMAIN" ]]; then
  echo "Open: https://${DOMAIN}"
else
  echo "HTTP-only mode enabled. Consider setting a domain + TLS later by editing .env:"
  echo "  APP_URL=https://finance.example.com"
  echo "  CADDY_ADDRESS=finance.example.com"
  echo "  ACME_EMAIL=you@example.com"
fi
