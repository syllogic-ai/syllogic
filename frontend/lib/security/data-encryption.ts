import {
  createCipheriv,
  createDecipheriv,
  createHmac,
  randomBytes,
} from "node:crypto";

const ENVELOPE_PREFIX = "enc:v1";

type EncryptionConfig = {
  currentKey: Buffer | null;
  previousKey: Buffer | null;
  keyId: string;
};

let cachedConfig: EncryptionConfig | null = null;

function parseKey(raw: string): Buffer {
  const value = raw.trim();
  if (!value) {
    throw new Error("Encryption key cannot be empty.");
  }

  if (/^[0-9a-fA-F]+$/.test(value) && value.length % 2 === 0) {
    const decoded = Buffer.from(value, "hex");
    if (decoded.length === 32) return decoded;
  }

  const padded = value + "=".repeat((4 - (value.length % 4)) % 4);
  const decoded = Buffer.from(padded, "base64");
  if (decoded.length === 32) return decoded;

  throw new Error("Data encryption key must decode to exactly 32 bytes.");
}

function getConfig(): EncryptionConfig {
  if (cachedConfig) {
    return cachedConfig;
  }

  const currentRaw = process.env.DATA_ENCRYPTION_KEY_CURRENT?.trim() ?? "";
  const previousRaw = process.env.DATA_ENCRYPTION_KEY_PREVIOUS?.trim() ?? "";
  const keyId = process.env.DATA_ENCRYPTION_KEY_ID?.trim() || "k1";

  cachedConfig = {
    currentKey: currentRaw ? parseKey(currentRaw) : null,
    previousKey: previousRaw ? parseKey(previousRaw) : null,
    keyId,
  };
  return cachedConfig;
}

function base64urlEncode(raw: Buffer): string {
  return raw
    .toString("base64")
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/g, "");
}

function base64urlDecode(raw: string): Buffer {
  const normalized = raw.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  return Buffer.from(padded, "base64");
}

function blindIndexKey(key: Buffer): Buffer {
  return createHmac("sha256", key).update("blind-index:v1").digest();
}

export function isDataEncryptionEnabled(): boolean {
  return Boolean(getConfig().currentKey);
}

export function encryptValue(plaintext: string | null): string | null {
  if (plaintext === null) {
    return null;
  }

  const config = getConfig();
  if (!config.currentKey) {
    return null;
  }

  const nonce = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", config.currentKey, nonce);
  const ciphertext = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  const payload = base64urlEncode(Buffer.concat([nonce, ciphertext, tag]));
  return `${ENVELOPE_PREFIX}:${config.keyId}:${payload}`;
}

export function decryptValue(ciphertext: string | null): string | null {
  if (ciphertext === null) {
    return null;
  }

  if (!ciphertext.startsWith(`${ENVELOPE_PREFIX}:`)) {
    return ciphertext;
  }

  const parts = ciphertext.split(":", 4);
  if (parts.length !== 4) {
    throw new Error("Invalid encrypted value format.");
  }

  const [, , embeddedKeyId, payload] = parts;
  const blob = base64urlDecode(payload);
  if (blob.length < 12 + 16) {
    throw new Error("Encrypted payload is too short.");
  }

  const nonce = blob.subarray(0, 12);
  const tag = blob.subarray(blob.length - 16);
  const encrypted = blob.subarray(12, blob.length - 16);

  const config = getConfig();
  if (!config.currentKey) {
    throw new Error("Encrypted data found but DATA_ENCRYPTION_KEY_CURRENT is not configured.");
  }

  const keyCandidates: Buffer[] = [];
  if (embeddedKeyId === config.keyId) {
    keyCandidates.push(config.currentKey);
    if (config.previousKey) keyCandidates.push(config.previousKey);
  } else {
    if (config.previousKey) keyCandidates.push(config.previousKey);
    keyCandidates.push(config.currentKey);
  }

  let lastError: unknown = null;
  for (const key of keyCandidates) {
    try {
      const decipher = createDecipheriv("aes-256-gcm", key, nonce);
      decipher.setAuthTag(tag);
      const decrypted = Buffer.concat([decipher.update(encrypted), decipher.final()]);
      return decrypted.toString("utf8");
    } catch (error) {
      lastError = error;
    }
  }

  const error = new Error("Failed to decrypt encrypted value with configured keys.");
  (error as Error & { cause?: unknown }).cause = lastError;
  throw error;
}

export function decryptWithFallback(
  ciphertext: string | null,
  plaintextFallback: string | null
): string | null {
  if (ciphertext) {
    try {
      return decryptValue(ciphertext);
    } catch {
      return plaintextFallback;
    }
  }
  return plaintextFallback;
}

export function blindIndex(value: string | null): string | null {
  if (value === null) return null;

  const config = getConfig();
  if (!config.currentKey) {
    return null;
  }

  return createHmac("sha256", blindIndexKey(config.currentKey)).update(value, "utf8").digest("hex");
}

export function blindIndexCandidates(value: string | null): string[] {
  if (value === null) return [];

  const config = getConfig();
  if (!config.currentKey) {
    return [];
  }

  const current = createHmac("sha256", blindIndexKey(config.currentKey))
    .update(value, "utf8")
    .digest("hex");
  if (!config.previousKey) {
    return [current];
  }

  const previous = createHmac("sha256", blindIndexKey(config.previousKey))
    .update(value, "utf8")
    .digest("hex");
  return previous === current ? [current] : [current, previous];
}
