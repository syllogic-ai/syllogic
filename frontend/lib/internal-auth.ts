import { createHmac } from "node:crypto";

export const INTERNAL_AUTH_USER_HEADER = "x-syllogic-user-id";
export const INTERNAL_AUTH_TIMESTAMP_HEADER = "x-syllogic-timestamp";
export const INTERNAL_AUTH_SIGNATURE_HEADER = "x-syllogic-signature";

interface InternalAuthSignatureInput {
  method: string;
  pathWithQuery: string;
  userId: string;
  timestamp?: string;
}

function getInternalAuthSecret(): string {
  const secret = process.env.INTERNAL_AUTH_SECRET?.trim();
  if (!secret) {
    throw new Error("INTERNAL_AUTH_SECRET is not configured");
  }
  return secret;
}

function buildSignaturePayload({
  method,
  pathWithQuery,
  userId,
  timestamp,
}: Required<InternalAuthSignatureInput>): string {
  return [method.toUpperCase(), pathWithQuery, userId, timestamp].join("\n");
}

export function createInternalAuthHeaders({
  method,
  pathWithQuery,
  userId,
  timestamp = Math.floor(Date.now() / 1000).toString(),
}: InternalAuthSignatureInput): Record<string, string> {
  const secret = getInternalAuthSecret();
  const payload = buildSignaturePayload({
    method,
    pathWithQuery,
    userId,
    timestamp,
  });
  const signature = createHmac("sha256", secret)
    .update(payload)
    .digest("hex");

  return {
    [INTERNAL_AUTH_USER_HEADER]: userId,
    [INTERNAL_AUTH_TIMESTAMP_HEADER]: timestamp,
    [INTERNAL_AUTH_SIGNATURE_HEADER]: signature,
  };
}
