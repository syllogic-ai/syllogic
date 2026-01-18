"use server";

import { revalidatePath } from "next/cache";
import { eq, and } from "drizzle-orm";
import { db } from "@/lib/db";
import { vehicles, type NewVehicle } from "@/lib/db/schema";
import { requireAuth } from "@/lib/auth-helpers";

export interface CreateVehicleInput {
  name: string;
  vehicleType: string;
  make?: string;
  model?: string;
  year?: number;
  currentValue?: number;
  currency: string;
}

export async function createVehicle(
  input: CreateVehicleInput
): Promise<{ success: boolean; error?: string; vehicleId?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const newVehicle: NewVehicle = {
      userId,
      name: input.name,
      vehicleType: input.vehicleType,
      make: input.make || null,
      model: input.model || null,
      year: input.year || null,
      currentValue: input.currentValue?.toString() || "0",
      currency: input.currency,
      isActive: true,
    };

    const [result] = await db.insert(vehicles).values(newVehicle).returning({ id: vehicles.id });

    revalidatePath("/");
    revalidatePath("/settings");
    return { success: true, vehicleId: result.id };
  } catch (error) {
    console.error("Failed to create vehicle:", error);
    return { success: false, error: "Failed to create vehicle" };
  }
}

export async function updateVehicle(
  vehicleId: string,
  input: Partial<CreateVehicleInput>
): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const vehicle = await db.query.vehicles.findFirst({
      where: and(eq(vehicles.id, vehicleId), eq(vehicles.userId, userId)),
    });

    if (!vehicle) {
      return { success: false, error: "Vehicle not found" };
    }

    await db
      .update(vehicles)
      .set({
        name: input.name,
        vehicleType: input.vehicleType,
        make: input.make,
        model: input.model,
        year: input.year,
        currentValue: input.currentValue?.toString(),
        currency: input.currency,
        updatedAt: new Date(),
      })
      .where(eq(vehicles.id, vehicleId));

    revalidatePath("/");
    revalidatePath("/settings");
    return { success: true };
  } catch (error) {
    console.error("Failed to update vehicle:", error);
    return { success: false, error: "Failed to update vehicle" };
  }
}

export async function deleteVehicle(
  vehicleId: string
): Promise<{ success: boolean; error?: string }> {
  const userId = await requireAuth();

  if (!userId) {
    return { success: false, error: "Not authenticated" };
  }

  try {
    const vehicle = await db.query.vehicles.findFirst({
      where: and(eq(vehicles.id, vehicleId), eq(vehicles.userId, userId)),
    });

    if (!vehicle) {
      return { success: false, error: "Vehicle not found" };
    }

    // Soft delete by setting isActive to false
    await db
      .update(vehicles)
      .set({
        isActive: false,
        updatedAt: new Date(),
      })
      .where(eq(vehicles.id, vehicleId));

    revalidatePath("/");
    revalidatePath("/settings");
    return { success: true };
  } catch (error) {
    console.error("Failed to delete vehicle:", error);
    return { success: false, error: "Failed to delete vehicle" };
  }
}

export async function getVehicles() {
  const userId = await requireAuth();

  if (!userId) {
    return [];
  }

  return db.query.vehicles.findMany({
    where: and(eq(vehicles.userId, userId), eq(vehicles.isActive, true)),
    orderBy: (vehicles, { asc }) => [asc(vehicles.name)],
  });
}

export async function getVehicle(vehicleId: string) {
  const userId = await requireAuth();

  if (!userId) {
    return null;
  }

  return db.query.vehicles.findFirst({
    where: and(
      eq(vehicles.id, vehicleId),
      eq(vehicles.userId, userId),
      eq(vehicles.isActive, true)
    ),
  });
}
