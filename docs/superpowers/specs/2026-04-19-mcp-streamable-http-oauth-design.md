# MCP Streamable HTTP + OAuth 2.1 — Design

**Date:** 2026-04-19
**Status:** Approved design, pending implementation plan
**Owner:** Giannis Kotsakiachidis

## Goal

Make the Syllogic MCP server usable from **remote Claude clients** (Claude.ai web, iOS, Android) in addition to the existing local stdio use (Claude Desktop, Claude Code), without breaking the current `pf_...` API-key workflow.

## Non-goals

- Supporting third-party app developers (no public app directory, no granular scopes beyond `mcp:access`).
- Migrating existing API-key users off API keys. Both auth paths stay indefinitely.
- Changing the MCP tool surface. Tool signatures and behavior are unchanged.

## Current state

- **MCP server**: Python FastMCP at `backend/mcp_server.py`. Already exposes Streamable HTTP via `mcp.http_app()`. Runs as a separate Railway service at `mcp.syllogic.ai`.
- **Auth**: Custom `ApiKeyAuthProvider` in `backend/app/mcp/auth.py` validating `pf_...` bearer tokens against the `api_keys` table (SHA-256 legacy, bcrypt new, auto-migrated on first use).
- **Frontend**: Next.js on `app.syllogic.ai` using **better-auth** (`frontend/lib/auth.ts`) with drizzle + Postgres, `admin()` plugin, email/password enabled.
- **Infra (all Railway)**: `app` (Next.js), `mcp` (FastMCP), `backend` (FastAPI), `worker`, `beat`, `postgres`, `redis`. All share the same Postgres instance.

## Why the migration is needed

The transport ("stdio → HTTP") is **already done**. The actual blocker is authentication: Claude.ai custom connectors require **OAuth 2.1 with RFC 7591 Dynamic Client Registration** per the [MCP 2025-11-25 authorization spec](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization). Our current bearer-token scheme doesn't speak that protocol.

## Architecture

```
┌─────────────────┐                    ┌──────────────────────┐
│  Claude.ai /    │  1. GET /mcp       │  mcp.syllogic.ai     │
│  Desktop / Code │ ─────────────────► │  (FastMCP / Python)  │
│                 │ ◄───────────────── │  RemoteAuthProvider  │
└─────────────────┘  2. 401 + WWW-Auth └──────────────────────┘
        │                                         ▲
        │  3. /.well-known/oauth-protected-       │  6. Verify JWT
        │     resource (discovers AS)             │     via JWKS
        ▼                                         │
┌──────────────────────┐                          │
│  app.syllogic.ai     │  4. DCR → consent ───────┘
│  Next.js +           │     → token issuance
│  better-auth +       │
│  @better-auth/       │  5. JWT (sub = userId,
│  oauth-provider      │       aud = mcp.syllogic.ai)
└──────────────────────┘
        │
        └─► shared Postgres (oauth_application, oauth_*_token, oauth_consent)
```

**Roles:**
- **Authorization Server (AS)** — `app.syllogic.ai`. Better-auth with `@better-auth/oauth-provider` plugin. Issues JWT access tokens + refresh tokens.
- **Resource Server (RS)** — `mcp.syllogic.ai`. FastMCP with a composite auth provider that accepts either a `pf_...` API key or a JWT signed by the AS.
- **Discovery** — RS serves `/.well-known/oauth-protected-resource`; AS serves `/.well-known/oauth-authorization-server` and `/.well-known/jwks.json`.

## Flow: Claude.ai connects for the first time

1. User adds `https://mcp.syllogic.ai/mcp` in Claude.ai → Settings → Connectors → Add custom connector.
2. Claude hits MCP without a token → receives `401 Unauthorized` with `WWW-Authenticate: Bearer resource_metadata="https://mcp.syllogic.ai/.well-known/oauth-protected-resource"`.
3. Claude fetches resource metadata → learns AS is `https://app.syllogic.ai`.
4. Claude fetches AS metadata → finds `registration_endpoint`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`.
5. Claude POSTs to `registration_endpoint` (DCR) → receives a fresh `client_id`.
6. Claude opens browser to `/api/auth/oauth2/authorize?...&resource=https://mcp.syllogic.ai&scope=mcp:access`.
7. If user isn't logged in to Syllogic → redirect to `/login?returnTo=...` (existing better-auth flow) → back to authorize.
8. Consent page `/oauth/consent` asks: "**Claude** is requesting access to your Syllogic financial data." User clicks **Allow**.
9. AS redirects back to Claude with auth code → Claude exchanges for JWT access token + refresh token.
10. Claude retries MCP call with `Authorization: Bearer <jwt>` → `CompositeAuthProvider` verifies signature against JWKS → extracts `sub` as `user_id` → tool runs.

## Component design

### 1. Authorization Server (Next.js, `app.syllogic.ai`)

**File modified:** `frontend/lib/auth.ts`
**Plugin added:** `@better-auth/oauth-provider`

```ts
import { oauthProvider } from "@better-auth/oauth-provider";

export const auth = betterAuth({
  // ... existing drizzleAdapter, admin(), emailAndPassword, session config
  plugins: [
    admin(),
    oauthProvider({
      allowDynamicClientRegistration: true,
      allowUnauthenticatedClientRegistration: true,
      issuer: "https://app.syllogic.ai",
      accessTokenExpiresIn: 60 * 60,             // 1 hour
      refreshTokenExpiresIn: 60 * 60 * 24 * 30,  // 30 days
      scopes: {
        "mcp:access": "Access your Syllogic financial data",
      },
      consentPage: "/oauth/consent",
    }),
  ],
});
```

**New routes (auto-mounted by the plugin):**
- `GET  /.well-known/oauth-authorization-server`
- `GET  /.well-known/jwks.json`
- `POST /api/auth/oauth2/register` (RFC 7591 DCR)
- `GET  /api/auth/oauth2/authorize`
- `POST /api/auth/oauth2/token`
- `POST /api/auth/oauth2/revoke`

**New DB tables** (via drizzle migration generated from the plugin's schema):
- `oauth_application` — DCR-registered clients
- `oauth_access_token`
- `oauth_refresh_token`
- `oauth_consent`

**New file:** `frontend/app/oauth/consent/page.tsx`
- Server component that reads the pending authorization request (client_id, scopes, redirect_uri)
- Renders: "**{client_name}** is requesting access to your Syllogic account. It will be able to view and update your financial data."
- Two forms posting to the plugin's consent-handler URL: **Allow** / **Deny**
- If user not authenticated: `redirect('/login?returnTo=' + encodeURIComponent(currentUrl))`

**JWT claims issued:**
```json
{
  "iss": "https://app.syllogic.ai",
  "sub": "<userId>",
  "aud": "https://mcp.syllogic.ai",
  "scope": "mcp:access",
  "client_id": "<DCR-issued client id>",
  "exp": "...",
  "iat": "..."
}
```

### 2. Resource Server (Python FastMCP, `mcp.syllogic.ai`)

**File modified:** `backend/app/mcp/auth.py` — add `CompositeAuthProvider`.
**File modified:** `backend/app/mcp/server.py` — swap `auth=ApiKeyAuthProvider()` for `auth=RemoteAuthProvider(token_verifier=CompositeAuthProvider(), ...)`.

```python
from fastmcp.server.auth import RemoteAuthProvider, AuthProvider, AccessToken
from fastmcp.server.auth.providers.jwt import JWTVerifier
from pydantic import AnyHttpUrl

class CompositeAuthProvider(AuthProvider):
    """Tries API key first (cheap, prefix-gated), falls back to JWT."""
    def __init__(self):
        self.api_key = ApiKeyAuthProvider()
        self.jwt = JWTVerifier(
            jwks_uri="https://app.syllogic.ai/.well-known/jwks.json",
            issuer="https://app.syllogic.ai",
            audience="https://mcp.syllogic.ai",
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        if token.startswith("pf_"):
            return await self.api_key.verify_token(token)
        at = await self.jwt.verify_token(token)
        if at is None:
            return None
        # Normalize: ensure claims["user_id"] is set from sub.
        # Reject tokens without a subject — an empty user_id would silently
        # authenticate as no one.
        if "user_id" not in at.claims:
            sub = at.claims.get("sub")
            if not sub:
                return None
            at.claims["user_id"] = sub
        return at


auth = RemoteAuthProvider(
    token_verifier=CompositeAuthProvider(),
    authorization_servers=[AnyHttpUrl("https://app.syllogic.ai")],
    base_url="https://mcp.syllogic.ai",
)

mcp = FastMCP(name="Syllogic MCP", instructions="...", auth=auth)
```

**Key invariants:**
- `get_mcp_user_id()` in `backend/app/db_helpers.py` already reads from the access token's claims. Both auth paths normalize to `claims["user_id"]`, so **no tool code changes**.
- `pf_` prefix gating prevents any token-type ambiguity.
- `RemoteAuthProvider` is the wrapper that makes FastMCP emit the `WWW-Authenticate` header and serve `/.well-known/oauth-protected-resource`.

## Migration steps (ordered)

1. Verify current HTTP deploy at `mcp.syllogic.ai/mcp` responds correctly with a `pf_` key (smoke test via MCP Inspector).
2. Install `@better-auth/oauth-provider` in frontend, add plugin to `auth.ts`, generate drizzle migration, apply to Postgres, deploy `app`.
3. Build `/oauth/consent` page.
4. Add `CompositeAuthProvider` and swap `RemoteAuthProvider` in MCP server. Deploy `mcp`.
5. End-to-end test: add custom connector in Claude.ai → verify DCR → consent → tool call loop.
6. Test from Claude iOS/Android with the same connector.
7. Update `frontend/lib/mcp/claude-desktop-config.ts` docs/UI to explain: Claude Code/Desktop → API key; Claude.ai web/mobile → custom connector URL.

## Testing strategy

**Unit (Python):**
- `CompositeAuthProvider.verify_token` with: valid `pf_`, invalid `pf_`, valid JWT, expired JWT, wrong-issuer JWT, wrong-audience JWT, malformed token, empty token.

**Integration (Python):**
- FastMCP test client with stubbed JWKS → call each tool with each token type → assert correct `user_id` resolution and data scoping.

**Integration (Next.js):**
- `POST /api/auth/oauth2/register` with a Claude-shaped DCR payload → assert 201 + `client_id`.
- End-to-end OAuth flow against a running dev instance with Playwright (login → authorize → consent → token exchange → introspect JWT).

**Manual / E2E:**
- Documented checklist for adding the connector in Claude.ai web, iOS, Android. Tool call from each. Covers DCR on a fresh install and refresh-token rotation after 1 hour.

**Regression:**
- Existing `pf_` key tests in `backend/` keep passing unchanged.

## Risks & mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| `allowUnauthenticatedClientRegistration` lets anyone register a client | DB bloat / spam | DCR creates a row but grants zero access until a real user consents. Rate-limit `/oauth2/register` by IP. Monitor `oauth_application` row count. |
| JWKS key rotation breaks live tokens | Auth outage | Rotate with overlap: publish new `kid` while keeping old. `JWTVerifier` handles `kid` lookup + cache refresh automatically. |
| Token audience misconfig (tokens valid for multiple resources) | Confused-deputy attacks | Hard-code `audience="https://mcp.syllogic.ai"` on both issuer and verifier. Reject tokens where `aud` doesn't match. |
| User confusion: API keys vs OAuth | Support burden | Clear UI copy: "Claude Desktop/Code → copy API key"; "Claude.ai web/mobile → paste this URL as a custom connector". |
| Consent page XSS from unvalidated `client_name` | Account takeover | Treat DCR-supplied strings as untrusted. Escape `client_name`, validate `redirect_uri` against plugin defaults (HTTPS only, no fragment). |

## Open questions

None blocking. All deployment domains confirmed (`app.syllogic.ai`, `mcp.syllogic.ai`). Shared Postgres confirmed.

## References

- [MCP Authorization spec (2025-11-25)](https://modelcontextprotocol.io/specification/2025-11-25/basic/authorization)
- [FastMCP RemoteAuthProvider](https://github.com/prefecthq/fastmcp/blob/main/docs/servers/auth/remote-oauth.mdx)
- [FastMCP JWTVerifier](https://github.com/prefecthq/fastmcp/tree/main/docs/servers/auth)
- [better-auth oauth-provider plugin](https://www.better-auth.com/docs/plugins/oauth-provider)
- [RFC 7591 — OAuth 2.0 Dynamic Client Registration](https://datatracker.ietf.org/doc/html/rfc7591)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707.html)
- [RFC 9728 — OAuth 2.0 Protected Resource Metadata](https://datatracker.ietf.org/doc/html/rfc9728)
