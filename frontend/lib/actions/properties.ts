"use server";

import { revalidatePath } from "next/cache";
import { eq, and } from "drizzle-orm";
import { db } from "@/lib/db";
import { properties, type NewProperty } from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";

export interface CreatePropertyInput {
  name: string;
  propertyType: string;
  address?: string;
  currentValue?: number;
  currency: string;
}

export async function createProperty(
  input: CreatePropertyInput
): Promise<{ success: boolean; error?: string; propertyId?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const newProperty: NewProperty = {
      userId,
      name: input.name,
      propertyType: input.propertyType,
      address: input.address || null,
      currentValue: input.currentValue?.toString() || "0",
      currency: input.currency,
      isActive: true,
    };

    const [result] = await db.insert(properties).values(newProperty).returning({ id: properties.id });

    revalidatePath("/");
    revalidatePath("/settings");
    return { success: true, propertyId: result.id };
  } catch (error) {
    console.error("Failed to create property:", error);
    return { success: false, error: "Failed to create property" };
  }
}

export async function updateProperty(
  propertyId: string,
  input: Partial<CreatePropertyInput>
): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const property = await db.query.properties.findFirst({
      where: and(eq(properties.id, propertyId), eq(properties.userId, userId)),
    });

    if (!property) {
      return { success: false, error: "Property not found" };
    }

    await db
      .update(properties)
      .set({
        name: input.name,
        propertyType: input.propertyType,
        address: input.address,
        currentValue: input.currentValue?.toString(),
        currency: input.currency,
        updatedAt: new Date(),
      })
      .where(eq(properties.id, propertyId));

    revalidatePath("/");
    revalidatePath("/settings");
    return { success: true };
  } catch (error) {
    console.error("Failed to update property:", error);
    return { success: false, error: "Failed to update property" };
  }
}

export async function deleteProperty(
  propertyId: string
): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const property = await db.query.properties.findFirst({
      where: and(eq(properties.id, propertyId), eq(properties.userId, userId)),
    });

    if (!property) {
      return { success: false, error: "Property not found" };
    }

    // Soft delete by setting isActive to false
    await db
      .update(properties)
      .set({
        isActive: false,
        updatedAt: new Date(),
      })
      .where(eq(properties.id, propertyId));

    revalidatePath("/");
    revalidatePath("/settings");
    return { success: true };
  } catch (error) {
    console.error("Failed to delete property:", error);
    return { success: false, error: "Failed to delete property" };
  }
}

export async function getProperties() {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  return db.query.properties.findMany({
    where: and(eq(properties.userId, userId), eq(properties.isActive, true)),
    orderBy: (properties, { asc }) => [asc(properties.name)],
  });
}

export async function getProperty(propertyId: string) {
  const userId = await requireAuth();

  if (!userId) {
    return null;
  }

  return db.query.properties.findFirst({
    where: and(
      eq(properties.id, propertyId),
      eq(properties.userId, userId),
      eq(properties.isActive, true)
    ),
  });
}
