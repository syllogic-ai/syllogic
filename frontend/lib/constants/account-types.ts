export const ACCOUNT_TYPES = [
  { value: "checking", label: "Checking Account" },
  { value: "savings", label: "Savings Account" },
  { value: "credit_card", label: "Credit Card" },
  { value: "investment", label: "Investment Account" },
  { value: "cash", label: "Cash" },
  { value: "other", label: "Other" },
] as const;

export type AccountTypeValue = (typeof ACCOUNT_TYPES)[number]["value"];
