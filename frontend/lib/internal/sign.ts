import { createHash, createHmac } from "node:crypto";

export type SignedFetchOpts = {
  method: string;
  userId: string;
  path: string; // exactly the path the backend will see
  body?: string;
  headers?: Record<string, string>;
};

function bodyHash(body: string | undefined): string {
  return createHash("sha256").update(body ?? "").digest("hex");
}

function sign(method: string, path: string, userId: string, ts: string, bodyHex: string): string {
  const secret = process.env.INTERNAL_AUTH_SECRET;
  if (!secret) throw new Error("INTERNAL_AUTH_SECRET not configured");
  const payload = [method.toUpperCase(), path, userId, ts, bodyHex].join("\n");
  return createHmac("sha256", secret).update(payload).digest("hex");
}

export async function signedFetch(url: string, opts: SignedFetchOpts): Promise<Response> {
  const ts = Math.floor(Date.now() / 1000).toString();
  const bodyHex = bodyHash(opts.body);
  const signature = sign(opts.method, opts.path, opts.userId, ts, bodyHex);
  const headers = {
    ...opts.headers,
    "x-syllogic-user-id": opts.userId,
    "x-syllogic-timestamp": ts,
    "x-syllogic-signature": signature,
  };
  return fetch(url, { method: opts.method, headers, body: opts.body });
}
