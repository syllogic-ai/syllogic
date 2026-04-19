"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";

type Props = {
  params: Record<string, string | string[] | undefined>;
};

export function ConsentForm({ params }: Props) {
  const [pending, setPending] = useState<"allow" | "deny" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function submit(decision: "allow" | "deny") {
    setPending(decision);
    setError(null);
    try {
      const oauthQuery = new URLSearchParams(
        Object.entries(params).flatMap(([k, v]) =>
          typeof v === "string" ? [[k, v] as [string, string]] : []
        )
      ).toString();
      const scope = typeof params.scope === "string" ? params.scope : undefined;
      const res = await fetch("/api/auth/oauth2/consent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          accept: decision === "allow",
          ...(scope ? { scope } : {}),
          oauth_query: oauthQuery,
        }),
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
      if (!res.ok) {
        throw new Error(body.error ?? `Request failed (${res.status})`);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Something went wrong. Try again."
      );
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="space-y-3">
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
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
