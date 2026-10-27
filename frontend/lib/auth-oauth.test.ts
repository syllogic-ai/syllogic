// @vitest-environment node
import { createHash, randomBytes } from "node:crypto";
import { beforeAll, describe, expect, it, vi } from "vitest";

// The real `auth` from lib/auth.ts, on better-auth's in-memory adapter instead of Postgres:
// the OAuth provider's configuration is what is under test, not drizzle.
const store: Record<string, unknown[]> = {};
vi.mock("@/lib/db", () => ({ db: {} }));
vi.mock("better-auth/adapters/drizzle", async () => {
  const { memoryAdapter } = await import("better-auth/adapters/memory");
  return { drizzleAdapter: () => memoryAdapter(store) };
});

const ORIGIN = "https://app.syllogic.example";
const RESOURCE = "https://mcp.syllogic.ai/mcp";
// A stand-in for Composio's callback; any https redirect URI behaves the same.
const CALLBACK = "https://backend.composio.example/api/v3/toolkits/auth/callback";

let auth: typeof import("./auth").auth;

beforeAll(async () => {
  process.env.APP_URL = ORIGIN;
  process.env.BETTER_AUTH_SECRET = "test-secret-at-least-32-characters-long!";
  for (const model of ["user", "session", "account", "verification", "oauthClient", "oauthAccessToken", "oauthRefreshToken", "oauthConsent", "jwks"]) {
    store[model] = [];
  }
  ({ auth } = await import("./auth"));
});

const json = (path: string, body: unknown, headers: Record<string, string> = {}) =>
  auth.handler(
    new Request(`${ORIGIN}/api/auth${path}`, {
      method: "POST",
      headers: { "content-type": "application/json", origin: ORIGIN, ...headers },
      body: JSON.stringify(body),
    }),
  );

const form = (path: string, params: Record<string, string>) =>
  auth.handler(
    new Request(`${ORIGIN}/api/auth${path}`, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(params),
    }),
  );

describe("an MCP client registered dynamically (RFC 7591), as Composio's DCR_OAUTH registers", () => {
  // Composio and Claude refresh rather than send the person back to sign in. Neither names a
  // scope here (Composio's docs do not say it sends one), so the defaults must carry both
  // `mcp:access` and `offline_access`, or no refresh token is ever issued and the connection
  // dies with its 30-day access token.
  // Mutation: `scopes: ["mcp:access"]` (no offline_access) -- RED (no refresh_token).
  it("registers without a session and gets a refresh token it can use", async () => {
    const registered = await json("/oauth2/register", {
      client_name: "Composio",
      redirect_uris: [CALLBACK],
      grant_types: ["authorization_code", "refresh_token"],
      response_types: ["code"],
    });
    expect([200, 201]).toContain(registered.status); // 1.6.5 answers 200; RFC 7591 says 201
    const client = (await registered.json()) as { client_id: string; scope: string };
    expect(client.scope.split(" ").sort()).toEqual(["mcp:access", "offline_access"]);

    const signedUp = await json("/sign-up/email", { email: "anna@example.com", password: "a-long-password-1", name: "Anna" });
    expect(signedUp.status).toBe(200);
    const cookie = (signedUp.headers.get("set-cookie") ?? "").split(",").map((c) => c.split(";")[0]).join("; ");

    const verifier = randomBytes(32).toString("base64url");
    const challenge = createHash("sha256").update(verifier).digest("base64url");
    const asked = await auth.handler(
      new Request(
        `${ORIGIN}/api/auth/oauth2/authorize?${new URLSearchParams({
          response_type: "code",
          client_id: client.client_id,
          redirect_uri: CALLBACK,
          state: "st",
          resource: RESOURCE,
          code_challenge: challenge,
          code_challenge_method: "S256",
        })}`,
        { headers: { cookie } },
      ),
    );
    const consentPage = new URL(asked.headers.get("location") ?? "", ORIGIN);
    expect(consentPage.pathname).toBe("/oauth/consent");
    const consented = await json("/oauth2/consent", { accept: true, oauth_query: consentPage.search.slice(1) }, { cookie });
    const back = new URL(((await consented.json()) as { url: string }).url);
    expect(back.origin + back.pathname).toBe(CALLBACK);

    const issued = await form("/oauth2/token", {
      grant_type: "authorization_code",
      client_id: client.client_id,
      code: back.searchParams.get("code") ?? "",
      redirect_uri: CALLBACK,
      code_verifier: verifier,
      resource: RESOURCE,
    });
    expect(issued.status).toBe(200);
    const tokens = (await issued.json()) as { access_token: string; refresh_token?: string };
    // A JWT for the MCP server's audience: what backend/app/mcp/auth.py's JWTVerifier accepts.
    const claims = JSON.parse(Buffer.from(tokens.access_token.split(".")[1], "base64url").toString());
    expect([claims.aud].flat()).toContain(RESOURCE);
    expect(tokens.refresh_token).toBeTruthy();

    const refreshed = await form("/oauth2/token", {
      grant_type: "refresh_token",
      client_id: client.client_id,
      refresh_token: tokens.refresh_token!,
      resource: RESOURCE,
    });
    expect(refreshed.status).toBe(200);
    const again = (await refreshed.json()) as { access_token: string };
    expect([JSON.parse(Buffer.from(again.access_token.split(".")[1], "base64url").toString()).aud].flat()).toContain(RESOURCE);
  });
});
