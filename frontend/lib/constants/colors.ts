export const CATEGORY_COLORS = [
  { name: "Amber", value: "#92400E" },
  { name: "Blue", value: "#1E40AF" },
  { name: "Green", value: "#047857" },
  { name: "Red", value: "#B91C1C" },
  { name: "Purple", value: "#5B21B6" },
  { name: "Teal", value: "#0F766E" },
  { name: "Pink", value: "#9D174D" },
  { name: "Indigo", value: "#3730A3" },
  { name: "Emerald", value: "#15803D" },
  { name: "Slate", value: "#334155" },
  { name: "Stone", value: "#44403C" },
  { name: "Zinc", value: "#52525B" },
] as const;

export type CategoryColor = (typeof CATEGORY_COLORS)[number];

export function getColorByValue(value: string): CategoryColor | undefined {
  return CATEGORY_COLORS.find((color) => color.value === value);
}

export function getColorByName(name: string): CategoryColor | undefined {
  return CATEGORY_COLORS.find((color) => color.name.toLowerCase() === name.toLowerCase());
}
