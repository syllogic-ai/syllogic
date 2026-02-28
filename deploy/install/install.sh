#!/usr/bin/env bash
set -euo pipefail

REPO="syllogic-ai/syllogic"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Please run as root (e.g. sudo ./install.sh)"
  exit 1
fi

VERSION="${1:-}"
if [[ -z "$VERSION" ]]; then
  echo "[install] No version specified — detecting latest release..."
  VERSION="$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
    | grep '"tag_name"' | head -1 | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')"
  if [[ -z "$VERSION" ]]; then
    echo "[install] Could not detect latest release. Specify a version manually:"
    echo "  ./install.sh v1.0.0"
    exit 1
  fi
  echo "[install] Latest release: $VERSION"
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
INTERNAL_AUTH_SECRET="$(openssl rand -hex 32)"
DATA_ENCRYPTION_KEY_CURRENT="$(openssl rand -base64 32)"

# ── Configuration ──────────────────────────────────────────────
# Accept config via env vars for non-interactive (curl | bash) use.
# For interactive use, the script prompts when values are missing.
#
#   DEPLOY_MODE   — "public" (default) or "lan"
#   DOMAIN        — required for public mode (e.g. finance.example.com)
#   ACME_EMAIL    — optional, for Let's Encrypt
#
# Examples:
#   # Non-interactive public:
#   DOMAIN=finance.example.com curl ... | sudo bash
#
#   # Non-interactive LAN:
#   DEPLOY_MODE=lan curl ... | sudo bash
# ───────────────────────────────────────────────────────────────

prompt() {
  local var_name="$1" prompt_text="$2" default="${3:-}"
  # If already set via env, use that value
  if [[ -n "${!var_name:-}" ]]; then
    return
  fi
  # Try interactive prompt via /dev/tty
  if [[ -t 0 ]] || [[ -e /dev/tty ]]; then
    printf "%s" "$prompt_text" >/dev/tty 2>/dev/null || true
    read -r "$var_name" </dev/tty 2>/dev/null || true
  fi
  # Apply default if still empty
  if [[ -z "${!var_name:-}" ]]; then
    eval "$var_name=\"$default\""
  fi
}

prompt DEPLOY_MODE "Deployment mode [public/lan] (default: lan): " "lan"
if [[ "$DEPLOY_MODE" != "public" && "$DEPLOY_MODE" != "lan" ]]; then
  echo "[install] Invalid mode '$DEPLOY_MODE'. Use 'public' or 'lan'."
  exit 1
fi

APP_URL=""
CADDY_ADDRESS=""
ACME_EMAIL="${ACME_EMAIL:-}"

if [[ "$DEPLOY_MODE" == "public" ]]; then
  prompt DOMAIN "Domain (required, e.g. finance.example.com): " ""
  if [[ -z "${DOMAIN:-}" ]]; then
    echo "[install] Public mode requires a domain. Set DOMAIN env var or use 'lan' mode:"
    echo "  DOMAIN=finance.example.com curl -fsSL ... | sudo bash"
    echo "  DEPLOY_MODE=lan curl -fsSL ... | sudo bash"
    exit 1
  fi

  prompt ACME_EMAIL "ACME email (for Let's Encrypt): " ""
  APP_URL="https://${DOMAIN}"
  CADDY_ADDRESS="${DOMAIN}"
  PORT_LINES="HTTP_PORT=8080
HTTPS_PORT=443"
else
  APP_URL="http://localhost:8080"
  CADDY_ADDRESS=":80"
  PORT_LINES="HTTP_PORT=8080"
  echo "[install] LAN mode selected. HTTP-only — not suitable for public internet exposure."
fi

# Only write .env if one doesn't already exist (preserve config on upgrades)
if [[ -f "$INSTALL_DIR/.env" ]]; then
  echo "[install] Existing .env found — preserving. Updating APP_VERSION only."
  sed -i.bak "s/^APP_VERSION=.*/APP_VERSION=${VERSION}/" "$INSTALL_DIR/.env"
  rm -f "$INSTALL_DIR/.env.bak"
else
  cat > "$INSTALL_DIR/.env" <<EOF
APP_VERSION=${VERSION}
APP_URL=${APP_URL}
BETTER_AUTH_SECRET=${BETTER_AUTH_SECRET}
INTERNAL_AUTH_SECRET=${INTERNAL_AUTH_SECRET}
CADDY_ADDRESS=${CADDY_ADDRESS}
ACME_EMAIL=${ACME_EMAIL}
${PORT_LINES}
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
DATA_ENCRYPTION_KEY_CURRENT=${DATA_ENCRYPTION_KEY_CURRENT}
DATA_ENCRYPTION_KEY_ID=k1

# --- Optional features ---

# AI-powered transaction categorization (OpenAI)
# OPENAI_API_KEY=sk-...

# Company logo lookup (logo.dev)
# LOGO_DEV_API_KEY=pk-...
EOF
fi

echo "[install] Starting services..."
cd "$INSTALL_DIR"
docker compose --env-file .env -f docker-compose.yml pull
docker compose --env-file .env -f docker-compose.yml up -d

echo
echo "[install] Done."
echo "- Config: $INSTALL_DIR/.env"
echo "- Stack:  cd $INSTALL_DIR && docker compose --env-file .env -f docker-compose.yml ps"
echo
if [[ "$DEPLOY_MODE" == "public" ]]; then
  echo "Open: https://${DOMAIN}"
else
  echo "Open: http://<your-ip>:8080"
  echo
  echo "To switch to public mode with TLS, edit $INSTALL_DIR/.env:"
  echo "  APP_URL=https://finance.example.com"
  echo "  CADDY_ADDRESS=finance.example.com"
  echo "  ACME_EMAIL=you@example.com"
fi
