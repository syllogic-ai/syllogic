# MCP Streamable HTTP + OAuth 2.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Syllogic MCP server usable as a Claude.ai custom connector from web and mobile by adding OAuth 2.1 with Dynamic Client Registration, while keeping the existing `pf_...` API-key flow intact.

**Architecture:** `app.syllogic.ai` (Next.js + better-auth) becomes the OAuth 2.1 Authorization Server via the `@better-auth/oauth-provider` plugin. `mcp.syllogic.ai` (Python FastMCP) becomes the Resource Server, with a composite auth provider that accepts either a `pf_` API key (existing DB path) or a JWT signed by the AS. Tool code is unchanged — both paths normalize to `claims["user_id"]`.

**Tech Stack:**
- Backend: Python 3.11+, FastMCP ≥2.14, FastAPI, SQLAlchemy, Postgres
- Frontend: Next.js 15 App Router, better-auth ^1.4, `@better-auth/oauth-provider`, drizzle-orm, drizzle-kit
- Infra: Railway (services: `app`, `mcp`, `backend`, `worker`, `beat`, `postgres`, `redis`)
- Spec reference: `docs/superpowers/specs/2026-04-19-mcp-streamable-http-oauth-design.md`

---

## File Structure

**Backend (Python, `mcp.syllogic.ai`):**
- Modify: `backend/app/mcp/auth.py` — add `CompositeAuthProvider` wrapping existing `ApiKeyAuthProvider` + a `JWTVerifier`
- Modify: `backend/app/mcp/server.py` — swap `auth=ApiKeyAuthProvider()` → `auth=RemoteAuthProvider(...)`
- Create: `backend/tests/test_mcp_composite_auth.py` — unit tests for the composite provider
- Create: `backend/tests/test_mcp_discovery.py` — smoke test for `/.well-known/oauth-protected-resource`

**Frontend (Next.js, `app.syllogic.ai`):**
- Modify: `frontend/package.json` — add `@better-auth/oauth-provider`
- Modify: `frontend/lib/auth.ts` — register `oauthProvider` plugin
- Modify: `frontend/lib/db/schema.ts` — add tables required by the plugin
- Create: `frontend/lib/db/migrations/NNNN_oauth_provider.sql` — drizzle migration (generated)
- Create: `frontend/app/oauth/consent/page.tsx` — consent screen shown to user during authorize
- Create: `frontend/app/oauth/consent/consent-form.tsx` — client component with Allow/Deny
- Create: `frontend/__tests__/oauth-dcr.test.ts` — DCR endpoint integration test
- Modify: `frontend/lib/mcp/claude-desktop-config.ts` — add helper + copy for "add as custom connector" URL

Each file has one responsibility. Consent page is split into a server component (reads authorization request) and a client component (form interaction) because better-auth's consent API requires both server data and client-side form posts.

---

## Pre-flight checks

Before starting, confirm:

- [ ] **Pre-1: Confirm FastMCP exports `RemoteAuthProvider` and `JWTVerifier`**

```bash
cd backend && python -c "from fastmcp.server.auth import RemoteAuthProvider; from fastmcp.server.auth.providers.jwt import JWTVerifier; print('ok')"
```
Expected: prints `ok`. If ImportError, bump `fastmcp` in `requirements.txt` to latest (`pip install -U fastmcp && pip freeze | grep fastmcp`) and record the version.

- [ ] **Pre-2: Confirm the better-auth OAuth provider plugin package name and API**

The plugin is distributed as a separate package. Open its README before coding:
```bash
npm view @better-auth/oauth-provider
```
If the package name differs (e.g. `better-auth-oauth-provider`), use that name wherever `@better-auth/oauth-provider` appears in this plan. Note the exact option names (`allowDynamicClientRegistration`, `allowUnauthenticatedClientRegistration`, `issuer`, `accessTokenExpiresIn`, `refreshTokenExpiresIn`, `scopes`, `consentPage`) and correct them in-plan before Task 4 if the plugin's current API has renamed anything.

---

## Phase A — Backend: composite auth provider

### Task 1: Add `CompositeAuthProvider` with unit tests (TDD)

**Files:**
- Create: `backend/tests/test_mcp_composite_auth.py`
- Modify: `backend/app/mcp/auth.py`

- [ ] **Step 1.1: Write failing tests**

```python
# backend/tests/test_mcp_composite_auth.py
"""Tests for CompositeAuthProvider (pf_ key + JWT)."""
import pytest
from unittest.mock import AsyncMock, patch

from app.mcp.auth import CompositeAuthProvider


@pytest.fixture
def provider():
    return CompositeAuthProvider()


class TestPfKeyRouting:
    @pytest.mark.asyncio
    async def test_pf_prefix_routes_to_api_key_provider(self, provider):
        fake_token = AsyncMock()
        fake_token.claims = {"user_id": "user_123"}
        with patch.object(
            provider.api_key, "verify_token", AsyncMock(return_value=fake_token)
        ) as m_api, patch.object(
            provider.jwt, "verify_token", AsyncMock()
        ) as m_jwt:
            result = await provider.verify_token("pf_abcdef123456")
        assert result is fake_token
        m_api.assert_awaited_once_with("pf_abcdef123456")
        m_jwt.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_pf_returns_none(self, provider):
        with patch.object(
            provider.api_key, "verify_token", AsyncMock(return_value=None)
        ), patch.object(
            provider.jwt, "verify_token", AsyncMock()
        ) as m_jwt:
            result = await provider.verify_token("pf_bogus")
        assert result is None
        m_jwt.assert_not_awaited()  # never falls through for pf_ prefix


class TestJwtRouting:
    @pytest.mark.asyncio
    async def test_non_pf_routes_to_jwt(self, provider):
        fake_token = AsyncMock()
        fake_token.claims = {"sub": "user_456"}
        with patch.object(
            provider.api_key, "verify_token", AsyncMock()
        ) as m_api, patch.object(
            provider.jwt, "verify_token", AsyncMock(return_value=fake_token)
        ):
            result = await provider.verify_token("eyJhbGciOi...")
        assert result is fake_token
        m_api.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_jwt_user_id_normalized_from_sub(self, provider):
        fake_token = AsyncMock()
        fake_token.claims = {"sub": "user_789"}  # no user_id key
        with patch.object(
            provider.jwt, "verify_token", AsyncMock(return_value=fake_token)
        ):
            result = await provider.verify_token("eyJhbGciOi...")
        assert result.claims["user_id"] == "user_789"
        assert result.claims["sub"] == "user_789"

    @pytest.mark.asyncio
    async def test_jwt_existing_user_id_preserved(self, provider):
        fake_token = AsyncMock()
        fake_token.claims = {"sub": "user_001", "user_id": "override_002"}
        with patch.object(
            provider.jwt, "verify_token", AsyncMock(return_value=fake_token)
        ):
            result = await provider.verify_token("eyJhbGciOi...")
        assert result.claims["user_id"] == "override_002"  # not overwritten

    @pytest.mark.asyncio
    async def test_invalid_jwt_returns_none(self, provider):
        with patch.object(
            provider.jwt, "verify_token", AsyncMock(return_value=None)
        ):
            result = await provider.verify_token("eyJhbGciOi.bad")
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_token_returns_none(self, provider):
        result = await provider.verify_token("")
        assert result is None
```

- [ ] **Step 1.2: Run tests to confirm they fail**

```bash
cd backend && pytest tests/test_mcp_composite_auth.py -v
```
Expected: collection error or `ImportError: cannot import name 'CompositeAuthProvider' from 'app.mcp.auth'`.

- [ ] **Step 1.3: Implement `CompositeAuthProvider`**

Add to `backend/app/mcp/auth.py` (below the existing `ApiKeyAuthProvider` class, do not remove anything):

```python
import os

try:
    from fastmcp.server.auth.providers.jwt import JWTVerifier
except ImportError:  # pragma: no cover
    JWTVerifier = None  # type: ignore


AS_ISSUER = os.environ.get("MCP_OAUTH_ISSUER", "https://app.syllogic.ai")
AS_JWKS_URI = os.environ.get(
    "MCP_OAUTH_JWKS_URI", "https://app.syllogic.ai/.well-known/jwks.json"
)
MCP_AUDIENCE = os.environ.get("MCP_OAUTH_AUDIENCE", "https://mcp.syllogic.ai")


class CompositeAuthProvider(AuthProvider):
    """
    Accepts either a pf_ API key (existing DB-backed) or a JWT issued by
    the Syllogic Authorization Server (better-auth on app.syllogic.ai).

    Prefix-gating: tokens starting with 'pf_' go to ApiKeyAuthProvider;
    everything else is treated as a JWT. This keeps the two paths fully
    disjoint, so a bad JWT never triggers a DB lookup and vice versa.
    """

    def __init__(self) -> None:
        if JWTVerifier is None:
            raise RuntimeError(
                "fastmcp.server.auth.providers.jwt.JWTVerifier is required "
                "for CompositeAuthProvider. Bump fastmcp."
            )
        self.api_key = ApiKeyAuthProvider()
        self.jwt = JWTVerifier(
            jwks_uri=AS_JWKS_URI,
            issuer=AS_ISSUER,
            audience=MCP_AUDIENCE,
        )

    async def verify_token(self, token: str) -> AccessToken | None:
        if not token:
            return None
        if token.startswith("pf_"):
            return await self.api_key.verify_token(token)
        access = await self.jwt.verify_token(token)
        if access is None:
            return None
        # Normalize: downstream tools read claims["user_id"].
        # Preserve an existing user_id claim if present.
        if "user_id" not in access.claims:
            access.claims["user_id"] = access.claims.get("sub", "")
        return access
```

- [ ] **Step 1.4: Install `pytest-asyncio` if missing, rerun tests to pass**

```bash
cd backend && pip install -q pytest-asyncio 2>/dev/null; pytest tests/test_mcp_composite_auth.py -v
```
Expected: 7 passed.
If `pytest-asyncio` wasn't already listed, add to `requirements-dev.txt` (or `requirements.txt` if no dev file).

- [ ] **Step 1.5: Commit**

```bash
git add backend/app/mcp/auth.py backend/tests/test_mcp_composite_auth.py
git commit -m "feat(mcp): add CompositeAuthProvider for pf_ keys + JWT"
```

---

### Task 2: Swap MCP server to `RemoteAuthProvider`

**Files:**
- Modify: `backend/app/mcp/server.py`
- Create: `backend/tests/test_mcp_discovery.py`

- [ ] **Step 2.1: Write a failing discovery test**

```python
# backend/tests/test_mcp_discovery.py
"""Smoke tests for the OAuth 2.0 Protected Resource Metadata endpoint."""
import pytest
from starlette.testclient import TestClient

# mcp_server.app is the ASGI app exposed by mcp.http_app()
from mcp_server import app


@pytest.fixture
def client():
    return TestClient(app)


def test_protected_resource_metadata_exposed(client):
    resp = client.get("/.well-known/oauth-protected-resource")
    assert resp.status_code == 200
    body = resp.json()
    # Must advertise our AS.
    assert "authorization_servers" in body
    servers = body["authorization_servers"]
    assert any("app.syllogic.ai" in str(s) for s in servers), body


def test_unauthenticated_request_returns_401_with_www_authenticate(client):
    # Any MCP POST without a token should get challenged.
    resp = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    assert resp.status_code == 401
    www_auth = resp.headers.get("www-authenticate", "")
    assert "Bearer" in www_auth
    assert "resource_metadata" in www_auth
```

- [ ] **Step 2.2: Run it to confirm it fails (wrong auth wired up still)**

```bash
cd backend && pytest tests/test_mcp_discovery.py -v
```
Expected: at minimum the `authorization_servers` assertion fails or endpoint 404s, because server is still using `ApiKeyAuthProvider` (which does not emit protected-resource metadata).

- [ ] **Step 2.3: Swap to `RemoteAuthProvider` in `server.py`**

In `backend/app/mcp/server.py`, replace the import block and `auth=` argument:

```python
# near the top
from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider
from pydantic import AnyHttpUrl

from app.db_helpers import get_mcp_user_id
from app.mcp.auth import CompositeAuthProvider, AS_ISSUER, MCP_AUDIENCE
from app.mcp.tools import accounts, categories, transactions, analytics, recurring

_auth = RemoteAuthProvider(
    token_verifier=CompositeAuthProvider(),
    authorization_servers=[AnyHttpUrl(AS_ISSUER)],
    base_url=MCP_AUDIENCE,
)

mcp = FastMCP(
    name="Syllogic MCP",
    instructions="""<unchanged — keep existing docstring>""",
    auth=_auth,
)
```
Leave every `@mcp.tool` definition below unchanged.

- [ ] **Step 2.4: Rerun tests to pass**

```bash
cd backend && pytest tests/test_mcp_discovery.py tests/test_mcp_composite_auth.py -v
```
Expected: all pass.

- [ ] **Step 2.5: Commit**

```bash
git add backend/app/mcp/server.py backend/tests/test_mcp_discovery.py
git commit -m "feat(mcp): wrap composite auth in RemoteAuthProvider"
```

---

### Task 3: Deploy backend with placeholder AS and verify existing `pf_` flow still works

**Goal:** don't block on frontend. Ship Task 1+2 now so `pf_` users are verified unchanged; JWT half stays dormant until frontend is live.

**Files:** none (deploy-only)

- [ ] **Step 3.1: Add env vars on Railway `mcp` service**

Set (Railway dashboard → `mcp` → Variables):
```
MCP_OAUTH_ISSUER=https://app.syllogic.ai
MCP_OAUTH_JWKS_URI=https://app.syllogic.ai/.well-known/jwks.json
MCP_OAUTH_AUDIENCE=https://mcp.syllogic.ai
```

- [ ] **Step 3.2: Deploy**

Push the branch, trigger Railway deploy on `mcp` service. Wait for "Deployed".

- [ ] **Step 3.3: Smoke-test existing `pf_` flow via curl**

```bash
# Replace $PF with a real pf_ key.
curl -s -X POST https://mcp.syllogic.ai/mcp \
  -H "Authorization: Bearer $PF" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | jq '.result.tools | length'
```
Expected: prints a number > 0 (tool list succeeds). If 401, double-check env vars and key validity.

- [ ] **Step 3.4: Smoke-test discovery**

```bash
curl -s https://mcp.syllogic.ai/.well-known/oauth-protected-resource | jq .
curl -s -X POST https://mcp.syllogic.ai/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' -i | grep -i www-authenticate
```
Expected: metadata JSON advertises `app.syllogic.ai`; unauthenticated POST returns `WWW-Authenticate: Bearer resource_metadata="..."`.

- [ ] **Step 3.5: Commit/tag (no code change, just a note)**

```bash
git tag -a mcp-remote-auth-deployed -m "mcp Resource Server live on mcp.syllogic.ai"
```
(Skip tag push if team doesn't use tags.)

---

## Phase B — Frontend: Authorization Server on `app.syllogic.ai`

### Task 4: Install `@better-auth/oauth-provider`

**Files:**
- Modify: `frontend/package.json`, `frontend/pnpm-lock.yaml` (or `package-lock.json` — use the manager already in use)

- [ ] **Step 4.1: Detect package manager**

```bash
cd frontend && ls -1 pnpm-lock.yaml yarn.lock package-lock.json 2>/dev/null
```
Use the one that exists (likely `pnpm-lock.yaml` or `package-lock.json`).

- [ ] **Step 4.2: Install the plugin**

With pnpm:
```bash
cd frontend && pnpm add @better-auth/oauth-provider
```
With npm:
```bash
cd frontend && npm install @better-auth/oauth-provider
```

If this exact name 404s (Pre-2 flagged), substitute the correct name now and do a single repo-wide find-and-replace of `@better-auth/oauth-provider` → correct name before continuing.

- [ ] **Step 4.3: Commit**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml
git commit -m "chore(frontend): add @better-auth/oauth-provider"
```

---

### Task 5: Generate and apply the drizzle migration for OAuth tables

**Files:**
- Modify: `frontend/lib/db/schema.ts` — import the plugin's drizzle schema and re-export
- Create: `frontend/lib/db/migrations/NNNN_oauth_provider.sql` (generated)

- [ ] **Step 5.1: Add the plugin's schema exports**

Open the plugin's README (from Pre-2) and find the documented drizzle schema snippet. If the plugin ships a helper like `oauthProviderSchema`, append to `frontend/lib/db/schema.ts`:

```ts
// near the bottom of frontend/lib/db/schema.ts
export {
  oauthApplication,
  oauthAccessToken,
  oauthRefreshToken,
  oauthConsent,
} from "@better-auth/oauth-provider/drizzle";
```

If the plugin instead ships raw table definitions to copy in, paste them verbatim into `schema.ts` as new `pgTable` declarations — do NOT hand-invent column names; use exactly what the plugin README specifies.

- [ ] **Step 5.2: Generate the migration**

```bash
cd frontend && pnpm db:generate
```
Expected: a new file appears under `frontend/lib/db/migrations/` (e.g. `0012_oauth_provider.sql`).

- [ ] **Step 5.3: Inspect the migration**

```bash
ls -lt frontend/lib/db/migrations/ | head -3
cat frontend/lib/db/migrations/<the-new-file>.sql
```
Sanity-check: it should `CREATE TABLE` for the 4 oauth tables (`oauth_client`, `oauth_access_token`, `oauth_refresh_token`, `oauth_consent`) plus the `jwks` table required by better-auth's `jwt` plugin (used by oauth-provider to sign JWTs). No accidental drops of existing tables.

- [ ] **Step 5.4: Apply the migration to local/dev Postgres first**

```bash
cd frontend && pnpm db:migrate
```
Expected: "Applied migration ..." with no errors.

- [ ] **Step 5.5: Commit**

```bash
git add frontend/lib/db/schema.ts frontend/lib/db/migrations
git commit -m "feat(db): add oauth-provider tables"
```

---

### Task 6: Register the `oauthProvider` plugin in `auth.ts`

**Files:**
- Modify: `frontend/lib/auth.ts`

- [ ] **Step 6.1: Add the plugin**

Edit `frontend/lib/auth.ts`. Add import at the top:

```ts
import { admin, jwt } from "better-auth/plugins";
import { oauthProvider } from "@better-auth/oauth-provider";
```

Inside `betterAuth({ ... plugins: [admin()], ... })`, replace the plugins array.
The `jwt()` plugin must come before `oauthProvider()` — the OAuth plugin calls
`getPlugin("jwt")` at init and throws `BetterAuthError("jwt_config")` if missing:

```ts
  plugins: [
    admin(),
    jwt(),
    oauthProvider({
      issuer: resolvedBaseURL ?? "https://app.syllogic.ai",
      allowDynamicClientRegistration: true,
      allowUnauthenticatedClientRegistration: true,
      accessTokenExpiresIn: 60 * 60,             // 1 hour
      refreshTokenExpiresIn: 60 * 60 * 24 * 30,  // 30 days
      scopes: {
        "mcp:access": "Access your Syllogic financial data",
      },
      consentPage: "/oauth/consent",
    }),
  ],
```

**Important:** If the plugin's current option names differ (per Pre-2), use the plugin's names — but the semantics (DCR on, unauthenticated DCR on, 1h access / 30d refresh, single `mcp:access` scope, consent at `/oauth/consent`) must match exactly.

- [ ] **Step 6.2: Verify the dev server boots and the well-known endpoints respond**

```bash
cd frontend && pnpm dev
```
In another terminal:
```bash
curl -s http://localhost:3000/.well-known/oauth-authorization-server | jq .
curl -s http://localhost:3000/.well-known/jwks.json | jq '.keys | length'
```
Expected: first prints metadata with `registration_endpoint`, `authorization_endpoint`, `token_endpoint`, `jwks_uri`. Second prints an integer ≥ 1.

- [ ] **Step 6.3: Commit**

```bash
git add frontend/lib/auth.ts
git commit -m "feat(auth): enable OAuth 2.1 provider with DCR"
```

---

### Task 7: Integration test — DCR endpoint accepts a Claude-shaped payload

**Files:**
- Create: `frontend/__tests__/oauth-dcr.test.ts`

- [ ] **Step 7.1: Write failing integration test**

```ts
// frontend/__tests__/oauth-dcr.test.ts
/**
 * Smoke test that Dynamic Client Registration works end-to-end
 * against a running dev server at http://localhost:3000.
 *
 * Run only after `pnpm dev` is up.
 */
import { describe, it, expect } from "vitest";

const BASE = process.env.TEST_BASE_URL ?? "http://localhost:3000";

describe("OAuth DCR", () => {
  it("registers a public client and returns client_id", async () => {
    const res = await fetch(`${BASE}/api/auth/oauth2/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        client_name: "Claude (Test)",
        redirect_uris: ["https://claude.ai/api/mcp/auth_callback"],
        grant_types: ["authorization_code", "refresh_token"],
        token_endpoint_auth_method: "none", // public client
        scope: "mcp:access",
      }),
    });

    expect(res.status).toBe(201);
    const body = await res.json();
    expect(body.client_id).toBeTruthy();
    expect(body.redirect_uris).toContain(
      "https://claude.ai/api/mcp/auth_callback",
    );
  });

  it("advertises registration endpoint in AS metadata", async () => {
    const res = await fetch(`${BASE}/.well-known/oauth-authorization-server`);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.registration_endpoint).toContain("/oauth2/register");
    expect(body.jwks_uri).toContain("/jwks");
  });
});
```

- [ ] **Step 7.2: Run test against running dev server**

```bash
# terminal A (already running from Task 6):
# pnpm dev

# terminal B:
cd frontend && pnpm vitest run __tests__/oauth-dcr.test.ts
```
Expected: 2 passed. If the registration URL is `/api/auth/oauth2/register` vs `/api/auth/oauth/register` (plugin version difference), adjust the test's URL to match what AS metadata advertises and re-run.

- [ ] **Step 7.3: Commit**

```bash
git add frontend/__tests__/oauth-dcr.test.ts
git commit -m "test(auth): DCR endpoint accepts Claude-shaped client"
```

---

### Task 8: Build the `/oauth/consent` page

**Files:**
- Create: `frontend/app/oauth/consent/page.tsx`
- Create: `frontend/app/oauth/consent/consent-form.tsx`

- [ ] **Step 8.1: Server component — reads pending authorization**

```tsx
// frontend/app/oauth/consent/page.tsx
import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { auth } from "@/lib/auth";
import { ConsentForm } from "./consent-form";

type SearchParams = {
  client_id?: string;
  scope?: string;
  redirect_uri?: string;
  state?: string;
  // plugin may pass an opaque consent_id; keep a catch-all
  [key: string]: string | string[] | undefined;
};

export default async function ConsentPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;

  // Require an authenticated user — if not, send them to login with returnTo.
  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    const returnTo = "/oauth/consent?" + new URLSearchParams(
      Object.entries(params).flatMap(([k, v]) =>
        typeof v === "string" ? [[k, v] as [string, string]] : [],
      ),
    ).toString();
    redirect(`/login?returnTo=${encodeURIComponent(returnTo)}`);
  }

  // Resolve client metadata (name, logo) by client_id.
  // better-auth exposes this via auth.api — the exact helper name is
  // plugin-specific; fall back to showing the raw client_id if unavailable.
  let clientName = params.client_id ?? "Unknown client";
  try {
    // If the plugin exposes a helper, use it here. Otherwise skip.
    // e.g.: const app = await auth.api.getOAuthApplication({ clientId: params.client_id! });
    // clientName = app?.name ?? clientName;
  } catch {
    /* show fallback */
  }

  const scopes = (params.scope ?? "").split(" ").filter(Boolean);

  return (
    <main className="mx-auto max-w-md p-6 space-y-6">
      <h1 className="text-2xl font-semibold">Authorize {clientName}</h1>
      <p className="text-sm text-muted-foreground">
        <strong>{clientName}</strong> is requesting access to your Syllogic
        account. If you approve, it will be able to:
      </p>
      <ul className="list-disc pl-6 text-sm">
        {scopes.includes("mcp:access") && (
          <li>View and update your financial data via the Syllogic MCP server</li>
        )}
        {scopes.length === 0 && <li>Access your Syllogic data</li>}
      </ul>
      <ConsentForm params={params} />
    </main>
  );
}
```

- [ ] **Step 8.2: Client component — Allow / Deny form**

```tsx
// frontend/app/oauth/consent/consent-form.tsx
"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button"; // adjust import path to existing UI kit

type Props = {
  params: Record<string, string | string[] | undefined>;
};

export function ConsentForm({ params }: Props) {
  const [pending, setPending] = useState<"allow" | "deny" | null>(null);

  async function submit(decision: "allow" | "deny") {
    setPending(decision);
    // The plugin exposes a server endpoint to finalize consent. Most versions
    // expose `/api/auth/oauth2/consent`. If AS metadata (or the plugin README)
    // names a different path, update here and in the test.
    const res = await fetch("/api/auth/oauth2/consent", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...params, decision }),
    });
    if (res.redirected) {
      window.location.assign(res.url);
      return;
    }
    const body = await res.json().catch(() => ({}));
    if (body.redirect_uri) {
      window.location.assign(body.redirect_uri);
      return;
    }
    setPending(null);
  }

  return (
    <div className="flex gap-3">
      <Button
        variant="default"
        disabled={pending !== null}
        onClick={() => submit("allow")}
      >
        {pending === "allow" ? "Authorizing…" : "Allow"}
      </Button>
      <Button
        variant="outline"
        disabled={pending !== null}
        onClick={() => submit("deny")}
      >
        Deny
      </Button>
    </div>
  );
}
```

- [ ] **Step 8.3: Manually verify the page renders**

```bash
# dev server still running
open "http://localhost:3000/oauth/consent?client_id=test&scope=mcp:access&state=xyz&redirect_uri=https://claude.ai/cb"
```
If not logged in, you get redirected to `/login`. Log in, return — should see the consent UI with Allow/Deny.

- [ ] **Step 8.4: Commit**

```bash
git add frontend/app/oauth/consent
git commit -m "feat(oauth): consent page for MCP authorization"
```

---

### Task 9: Deploy frontend + run full OAuth flow manually

**Files:** none (deploy + manual test)

- [ ] **Step 9.1: Push branch and deploy `app` service on Railway**

Push and wait for `app.syllogic.ai` to redeploy.

- [ ] **Step 9.2: Production smoke-test — discovery endpoints**

```bash
curl -s https://app.syllogic.ai/.well-known/oauth-authorization-server | jq '{issuer, authorization_endpoint, token_endpoint, registration_endpoint, jwks_uri}'
curl -s https://app.syllogic.ai/.well-known/jwks.json | jq '.keys[0].kid'
```
Expected: all fields present and non-null.

- [ ] **Step 9.3: End-to-end test via MCP Inspector (before Claude.ai)**

```bash
npx @modelcontextprotocol/inspector
```
In the UI, add server URL `https://mcp.syllogic.ai/mcp` and choose OAuth. Inspector performs DCR → opens browser → you log in on `app.syllogic.ai` → consent → back to Inspector authenticated. Call `list_categories` → returns data scoped to your user.

- [ ] **Step 9.4: End-to-end in Claude.ai**

In Claude.ai → Settings → Connectors → **Add custom connector** → enter `https://mcp.syllogic.ai/mcp`. Go through the browser auth flow. Once connected, ask Claude: *"List my Syllogic accounts."* → should work.

- [ ] **Step 9.5: Repeat from Claude iOS or Android**

Same connector URL. Complete the mobile-browser OAuth flow. Confirm tools respond.

- [ ] **Step 9.6: Commit a note to the plan (optional)**

No code change; if the above worked, you're done.

---

### Task 10: Update onboarding copy to explain both auth paths

**Files:**
- Modify: `frontend/lib/mcp/claude-desktop-config.ts`
- Modify: wherever the "how to connect Claude" UI lives (search for the Claude desktop config string)

- [ ] **Step 10.1: Find the onboarding UI**

```bash
cd frontend && grep -rn "claude_desktop_config\|Claude Desktop\|mcpServers" app components --include="*.tsx" | head -20
```
Pick the page that shows the user their `pf_` key and copy-paste config.

- [ ] **Step 10.2: Add a section for custom connectors**

Alongside the existing "Claude Desktop / Code: copy this config" block, add:

```tsx
// in the same settings/connectors UI file
<section className="space-y-2">
  <h3 className="font-semibold">Claude on the web, iOS, or Android</h3>
  <p className="text-sm text-muted-foreground">
    In Claude settings, go to <strong>Connectors → Add custom connector</strong>{" "}
    and paste this URL:
  </p>
  <CopyBox value="https://mcp.syllogic.ai/mcp" />
  <p className="text-xs text-muted-foreground">
    You&apos;ll be redirected here to log in and approve access. No API key
    needed.
  </p>
</section>
```
Reuse the existing `CopyBox`/copy-to-clipboard component already used for the API key.

- [ ] **Step 10.3: Commit**

```bash
git add frontend/app frontend/components frontend/lib/mcp/claude-desktop-config.ts
git commit -m "docs(ui): explain custom-connector URL alongside API key"
```

---

### Task 11: PR and merge

- [ ] **Step 11.1: Open PR**

```bash
gh pr create --title "Enable Claude.ai custom connector via OAuth 2.1 on MCP server" --body "$(cat <<'EOF'
## Summary

- Add composite auth (pf_ key + OAuth JWT) to FastMCP server on mcp.syllogic.ai
- Register @better-auth/oauth-provider on app.syllogic.ai (DCR, JWKS, consent page)
- Existing pf_ flow is untouched; Claude Desktop / Code keep working

## Test plan

- [ ] Unit: backend pytest suite passes (6 new composite-auth tests)
- [ ] Unit: backend discovery test passes
- [ ] Integration: vitest DCR test passes against dev server
- [ ] Manual: MCP Inspector completes OAuth flow end-to-end
- [ ] Manual: Claude.ai web custom connector works
- [ ] Manual: Claude iOS/Android custom connector works
- [ ] Regression: existing Claude Desktop pf_ connection still works

Spec: docs/superpowers/specs/2026-04-19-mcp-streamable-http-oauth-design.md
EOF
)"
```

- [ ] **Step 11.2: After review + merge**

Delete the worktree branch per repo convention.

---

## Self-review notes (plan author → self)

- **Spec coverage:** every Section in the spec (Architecture, Component design AS, Component design RS, Migration, Testing, Risks) maps to a task here:
  - Architecture + Flow → Tasks 2, 3, 9 (discovery + E2E)
  - AS component (plugin, consent page, migration) → Tasks 4, 5, 6, 8
  - RS component (composite provider, RemoteAuthProvider) → Tasks 1, 2
  - Migration steps from spec (§Migration plan) → Tasks 3, 9
  - Testing strategy → Tasks 1, 2, 7, 9
  - Risks — `allowUnauthenticatedClientRegistration` concern is implicit in Task 6 config; rate-limiting `/oauth2/register` is deliberately NOT in this plan (follow-up task; not blocking Claude.ai connector)
- **Placeholder scan:** only intentional conditional instructions remain (e.g. "if package name 404s, substitute"). No TODO/TBD. All code blocks complete.
- **Type/name consistency:** `CompositeAuthProvider`, `RemoteAuthProvider`, `AS_ISSUER`, `MCP_AUDIENCE` used consistently across Tasks 1, 2, 3. Env var names identical in server config and Railway step.
- **Known inference:** exact option names on `@better-auth/oauth-provider` are inferred from the plugin README excerpt; Pre-2 enforces verification before Task 6.
