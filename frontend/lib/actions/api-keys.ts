"use server";

import crypto from "crypto";
import { db } from "@/lib/db";
import { apiKeys } from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";
import { revalidatePath } from "next/cache";
import { eq, and, desc } from "drizzle-orm";

function generateApiKey(): string {
  // Generate a secure random key: pf_ prefix + 32 base64url characters
  return `pf_${crypto.randomBytes(24).toString("base64url")}`;
}

function hashApiKey(key: string): string {
  return crypto.createHash("sha256").update(key).digest("hex");
}

export async function createApiKey(input: {
  name: string;
  expiresAt?: Date | null;
}): Promise<{
  success: boolean;
  error?: string;
  apiKey?: string;
  keyData?: {
    id: string;
    name: string;
    keyPrefix: string;
    createdAt: Date | null;
    expiresAt: Date | null;
  };
}> {
  const userId = await requireAuth();
  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  const trimmedName = input.name.trim();
  if (!trimmedName) {
    return { success: false, error: "Name is required" };
  }

  try {
    const rawKey = generateApiKey();
    const keyHash = hashApiKey(rawKey);
    const keyPrefix = rawKey.substring(0, 11); // "pf_" + 8 chars

    const [inserted] = await db
      .insert(apiKeys)
      .values({
        userId,
        name: trimmedName,
        keyHash,
        keyPrefix,
        expiresAt: input.expiresAt || null,
      })
      .returning();

    revalidatePath("/settings");

    return {
      success: true,
      apiKey: rawKey, // Only returned once, never stored
      keyData: {
        id: inserted.id,
        name: inserted.name,
        keyPrefix: inserted.keyPrefix,
        createdAt: inserted.createdAt,
        expiresAt: inserted.expiresAt,
      },
    };
  } catch (error) {
    console.error("Failed to create API key:", error);
    return { success: false, error: "Failed to create API key" };
  }
}

export async function listApiKeys(): Promise<{
  success: boolean;
  error?: string;
  keys?: Array<{
    id: string;
    name: string;
    keyPrefix: string;
    lastUsedAt: Date | null;
    expiresAt: Date | null;
    createdAt: Date | null;
  }>;
}> {
  const userId = await requireAuth();
  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const keys = await db.query.apiKeys.findMany({
      where: eq(apiKeys.userId, userId),
      orderBy: [desc(apiKeys.createdAt)],
      columns: {
        id: true,
        name: true,
        keyPrefix: true,
        lastUsedAt: true,
        expiresAt: true,
        createdAt: true,
      },
    });

    return { success: true, keys };
  } catch (error) {
    console.error("Failed to list API keys:", error);
    return { success: false, error: "Failed to list API keys" };
  }
}

export async function deleteApiKey(keyId: string): Promise<{
  success: boolean;
  error?: string;
}> {
  const userId = await requireAuth();
  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const deleted = await db
      .delete(apiKeys)
      .where(and(eq(apiKeys.id, keyId), eq(apiKeys.userId, userId)))
      .returning({ id: apiKeys.id });

    if (deleted.length === 0) {
      return { success: false, error: "API key not found" };
    }

    revalidatePath("/settings");
    return { success: true };
  } catch (error) {
    console.error("Failed to delete API key:", error);
    return { success: false, error: "Failed to delete API key" };
  }
}
