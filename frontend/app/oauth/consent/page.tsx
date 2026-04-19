import { notFound, redirect } from "next/navigation";
import { headers } from "next/headers";
import { eq } from "drizzle-orm";
import { auth } from "@/lib/auth";
import { db } from "@/lib/db";
import { oauthClient } from "@/lib/db/schema";
import { ConsentForm } from "./consent-form";

type SearchParams = {
  client_id?: string;
  scope?: string;
  redirect_uri?: string;
  state?: string;
  [key: string]: string | string[] | undefined;
};

const SCOPE_DESCRIPTIONS: Record<string, string> = {
  "mcp:access":
    "View and update your financial data via the Syllogic MCP server",
};

export default async function ConsentPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;

  const session = await auth.api.getSession({ headers: await headers() });
  if (!session) {
    const returnTo =
      "/oauth/consent?" +
      new URLSearchParams(
        Object.entries(params).flatMap(([k, v]) =>
          typeof v === "string" ? [[k, v] as [string, string]] : []
        )
      ).toString();
    redirect(`/login?returnTo=${encodeURIComponent(returnTo)}`);
  }

  const clientId = typeof params.client_id === "string" ? params.client_id : "";
  if (!clientId) notFound();

  const [client] = await db
    .select({
      name: oauthClient.name,
      disabled: oauthClient.disabled,
      scopes: oauthClient.scopes,
    })
    .from(oauthClient)
    .where(eq(oauthClient.clientId, clientId))
    .limit(1);

  if (!client || client.disabled) notFound();

  const clientName = client.name?.trim() || clientId;
  const allowedScopes = new Set(client.scopes ?? []);
  const requestedScopes = (params.scope ?? "").split(" ").filter(Boolean);
  const scopes = requestedScopes.filter((scope) => allowedScopes.has(scope));

  return (
    <main className="mx-auto max-w-md p-6 space-y-6">
      <h1 className="text-2xl font-semibold">Authorize {clientName}</h1>
      <p className="text-sm text-muted-foreground">
        <strong>{clientName}</strong> is requesting access to your Syllogic
        account. If you approve, it will be able to:
      </p>
      <ul className="list-disc pl-6 text-sm">
        {scopes.length === 0 && <li>Access your Syllogic data</li>}
        {scopes.map((scope) => (
          <li key={scope}>
            {SCOPE_DESCRIPTIONS[scope] ?? (
              <>
                <code className="rounded bg-muted px-1 font-mono">{scope}</code>{" "}
                (additional access)
              </>
            )}
          </li>
        ))}
      </ul>
      <ConsentForm params={params} />
    </main>
  );
}
