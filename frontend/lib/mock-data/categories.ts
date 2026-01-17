// Mock categories for UI testing
// This file should be removed or replaced when connected to real database

export interface MockCategory {
  id: string;
  name: string;
  color: string;
  icon: string;
  categoryType: "expense" | "income" | "transfer";
}

export const mockCategories: MockCategory[] = [
  { id: "cat-1", name: "Meals", color: "#92400E", icon: "RiRestaurantLine", categoryType: "expense" },
  { id: "cat-2", name: "Software", color: "#1E40AF", icon: "RiCodeLine", categoryType: "expense" },
  { id: "cat-3", name: "Equipment", color: "#3730A3", icon: "RiComputerLine", categoryType: "expense" },
  { id: "cat-4", name: "Transportation", color: "#047857", icon: "RiCarLine", categoryType: "expense" },
  { id: "cat-5", name: "Utilities", color: "#B91C1C", icon: "RiLightbulbLine", categoryType: "expense" },
  { id: "cat-6", name: "Entertainment", color: "#9D174D", icon: "RiMovieLine", categoryType: "expense" },
  { id: "cat-7", name: "Shopping", color: "#5B21B6", icon: "RiShoppingBagLine", categoryType: "expense" },
  { id: "cat-8", name: "Healthcare", color: "#0F766E", icon: "RiHospitalLine", categoryType: "expense" },
  { id: "cat-9", name: "Income", color: "#15803D", icon: "RiWalletLine", categoryType: "income" },
  { id: "cat-10", name: "Transfer", color: "#334155", icon: "RiExchangeLine", categoryType: "transfer" },
  { id: "cat-11", name: "Other", color: "#44403C", icon: "RiMoreLine", categoryType: "expense" },
  { id: "cat-12", name: "Uncategorized", color: "#52525B", icon: "RiQuestionLine", categoryType: "expense" },
];

export function getCategoryById(id: string): MockCategory | undefined {
  return mockCategories.find((cat) => cat.id === id);
}

export function getCategoriesByType(type: "expense" | "income" | "transfer"): MockCategory[] {
  return mockCategories.filter((cat) => cat.categoryType === type);
}
