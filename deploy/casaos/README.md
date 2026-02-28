# CasaOS Deployment

This folder contains the CasaOS-ready compose bundle for Syllogic.

## Quick Start

1. Open CasaOS App Store custom install (or use `docker compose` manually).
2. Copy `.env.example` to `.env`.
3. Set required values:
   - `POSTGRES_PASSWORD`
   - `BETTER_AUTH_SECRET`
   - `INTERNAL_AUTH_SECRET`
   - `DATA_ENCRYPTION_KEY_CURRENT` (recommended for production)
   - `DATA_ENCRYPTION_KEY_ID` (recommended, e.g. `k1`)
   - `APP_URL` (usually `http://<your-casaos-ip>:<WEBUI_PORT>`)
4. Start the stack from CasaOS UI.

If you start manually:

```bash
cd deploy/casaos
docker compose up -d
```

## Notes

- `APP_VERSION=edge` tracks latest main image.
- Set `APP_VERSION` to a release tag (for example `v1.2.3`) for stable production pinning.
- `DATA_ENCRYPTION_KEY_PREVIOUS` is optional and used for key rotation fallback.
- API routes are proxied through the app (`/api/*`) so internal signed auth works correctly.
- MCP is exposed on `MCP_PORT` (default `8001`).
