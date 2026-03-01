import {
  differenceInCalendarDays,
  endOfDay,
  startOfDay,
  subDays,
} from "date-fns";
import { CATEGORY_COLORS } from "@/lib/constants/colors";

export function formatIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function parseIsoDateAtStartOfDay(isoDate: string): Date {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day, 0, 0, 0, 0);
}

export function parseIsoDateAtEndOfDay(isoDate: string): Date {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day, 23, 59, 59, 999);
}

export function getTouchedMonthKeys(startDate: Date, endDate: Date): string[] {
  const keys: string[] = [];
  const lastMonth = new Date(endDate.getFullYear(), endDate.getMonth(), 1);

  for (
    let cursor = new Date(startDate.getFullYear(), startDate.getMonth(), 1);
    cursor <= lastMonth;
    cursor = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 1)
  ) {
    keys.push(`${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}`);
  }

  return keys;
}

export function computePreviousWindow(startDate: Date, endDate: Date): {
  comparisonStart: Date;
  comparisonEnd: Date;
  spanDays: number;
} {
  const normalizedStart = startOfDay(startDate);
  const normalizedEnd = endOfDay(endDate);
  const spanDays = Math.max(1, differenceInCalendarDays(normalizedEnd, normalizedStart) + 1);

  const comparisonEnd = endOfDay(subDays(normalizedStart, 1));
  const comparisonStart = startOfDay(subDays(comparisonEnd, spanDays - 1));

  return {
    comparisonStart,
    comparisonEnd,
    spanDays,
  };
}

export function resolveCategoryColor(
  color: string | null | undefined,
  index: number
): string {
  if (color && color.trim().length > 0) {
    return color;
  }

  return CATEGORY_COLORS[index % CATEGORY_COLORS.length].value;
}
