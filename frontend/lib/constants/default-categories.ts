import { CATEGORY_COLORS } from "./colors";

export type CategoryType = "expense" | "income" | "transfer";

export interface DefaultCategory {
  name: string;
  categoryType: CategoryType;
  color: string;
  icon: string;
  description?: string;
  isSystem?: boolean;
}

export const DEFAULT_EXPENSE_CATEGORIES: DefaultCategory[] = [
  {
    name: "Food & Dining",
    categoryType: "expense",
    color: CATEGORY_COLORS[0].value, // Amber
    icon: "RiRestaurantLine",
    description: "Restaurants, groceries, food delivery",
  },
  {
    name: "Transportation",
    categoryType: "expense",
    color: CATEGORY_COLORS[1].value, // Blue
    icon: "RiCarLine",
    description: "Fuel, public transit, parking, ride-sharing",
  },
  {
    name: "Shopping",
    categoryType: "expense",
    color: CATEGORY_COLORS[6].value, // Pink
    icon: "RiShoppingBagLine",
    description: "Clothing, electronics, general purchases",
  },
  {
    name: "Entertainment",
    categoryType: "expense",
    color: CATEGORY_COLORS[4].value, // Purple
    icon: "RiGamepadLine",
    description: "Movies, games, concerts, streaming services",
  },
  {
    name: "Bills & Utilities",
    categoryType: "expense",
    color: CATEGORY_COLORS[9].value, // Slate
    icon: "RiFileTextLine",
    description: "Electricity, water, internet, phone",
  },
  {
    name: "Health & Fitness",
    categoryType: "expense",
    color: CATEGORY_COLORS[2].value, // Green
    icon: "RiHeartPulseLine",
    description: "Gym, medical expenses, pharmacy",
  },
  {
    name: "Housing",
    categoryType: "expense",
    color: CATEGORY_COLORS[10].value, // Stone
    icon: "RiHome4Line",
    description: "Rent, mortgage, home maintenance",
  },
  {
    name: "Education",
    categoryType: "expense",
    color: CATEGORY_COLORS[7].value, // Indigo
    icon: "RiBookOpenLine",
    description: "Courses, books, tuition, training",
  },
  {
    name: "Travel",
    categoryType: "expense",
    color: CATEGORY_COLORS[5].value, // Teal
    icon: "RiPlaneLine",
    description: "Hotels, flights, vacation expenses",
  },
  {
    name: "Personal Care",
    categoryType: "expense",
    color: CATEGORY_COLORS[8].value, // Emerald
    icon: "RiUser3Line",
    description: "Haircuts, spa, personal hygiene",
  },
  {
    name: "Gifts & Donations",
    categoryType: "expense",
    color: CATEGORY_COLORS[3].value, // Red
    icon: "RiGiftLine",
    description: "Presents, charity donations",
  },
  {
    name: "Other Expenses",
    categoryType: "expense",
    color: CATEGORY_COLORS[11].value, // Zinc
    icon: "RiMore2Line",
    description: "Miscellaneous expenses",
  },
];

export const DEFAULT_INCOME_CATEGORIES: DefaultCategory[] = [
  {
    name: "Salary",
    categoryType: "income",
    color: CATEGORY_COLORS[2].value, // Green
    icon: "RiBriefcaseLine",
    description: "Regular employment income",
  },
  {
    name: "Freelance",
    categoryType: "income",
    color: CATEGORY_COLORS[5].value, // Teal
    icon: "RiComputerLine",
    description: "Freelance and contract work",
  },
  {
    name: "Investment",
    categoryType: "income",
    color: CATEGORY_COLORS[1].value, // Blue
    icon: "RiLineChartLine",
    description: "Dividends, interest, capital gains",
  },
  {
    name: "Other Income",
    categoryType: "income",
    color: CATEGORY_COLORS[8].value, // Emerald
    icon: "RiAddCircleLine",
    description: "Miscellaneous income",
  },
];

export const DEFAULT_TRANSFER_CATEGORIES: DefaultCategory[] = [
  {
    name: "Internal Transfer",
    categoryType: "transfer",
    color: CATEGORY_COLORS[9].value, // Slate
    icon: "RiExchangeLine",
    description: "Transfers between your own accounts",
    isSystem: true,
  },
  {
    name: "Balancing Transfer",
    categoryType: "transfer",
    color: CATEGORY_COLORS[11].value, // Zinc
    icon: "RiScalesLine",
    description: "Balance adjustments for account reconciliation",
    isSystem: true,
  },
];

export const DEFAULT_CATEGORIES: DefaultCategory[] = [
  ...DEFAULT_EXPENSE_CATEGORIES,
  ...DEFAULT_INCOME_CATEGORIES,
  ...DEFAULT_TRANSFER_CATEGORIES,
];

export function getCategoriesByType(type: CategoryType): DefaultCategory[] {
  return DEFAULT_CATEGORIES.filter((category) => category.categoryType === type);
}
