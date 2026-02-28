"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

const STORAGE_KEY = "syllogic.walkthrough.completed";

export interface WalkthroughStep {
  id: string;
  title: string;
  content: string;
  target?: string;
}

export interface PageConfig {
  page: string;
  overview: string;
  steps: WalkthroughStep[];
}

export interface WalkthroughState {
  isActive: boolean;
  currentPage: string | null;
  currentStepIndex: number;
  showOverview: boolean;
  completedPages: string[];
  /** Persisted userId for per-user completion state */
  userId: string | null;
  startWalkthrough: (page: string) => void;
  nextStep: () => void;
  previousStep: () => void;
  skipWalkthrough: () => void;
  closeOverview: () => void;
  openOverview: (page: string) => void;
  hasCompletedPage: (page: string) => boolean;
  /** Sync completed state with current user; clears if user changed */
  syncWithUser: (userId: string) => void;
}

export const useWalkthroughStore = create<WalkthroughState>()(
  persist(
    (set, get) => ({
      isActive: false,
      currentPage: null,
      currentStepIndex: 0,
      showOverview: false,
      completedPages: [],
      userId: null,

      startWalkthrough: (page: string) => {
        set({
          isActive: true,
          currentPage: page,
          currentStepIndex: 0,
          showOverview: false,
        });
      },

      nextStep: () => {
        const { currentPage, currentStepIndex } = get();
        if (!currentPage) return;

        const config = PAGE_CONFIGS[currentPage as keyof typeof PAGE_CONFIGS];
        const steps = config?.steps ?? [];
        const isLastStep = currentStepIndex >= steps.length - 1;

        if (isLastStep) {
          const pages = get().completedPages;
          const nextPages = pages.includes(currentPage)
            ? pages
            : [...pages, currentPage];
          set({
            isActive: false,
            currentPage: null,
            currentStepIndex: 0,
            completedPages: nextPages,
          });
        } else {
          set({ currentStepIndex: currentStepIndex + 1 });
        }
      },

      previousStep: () => {
        const { currentStepIndex } = get();
        if (currentStepIndex <= 0) return;
        set({ currentStepIndex: currentStepIndex - 1 });
      },

      skipWalkthrough: () => {
        set({
          isActive: false,
          currentPage: null,
          currentStepIndex: 0,
          showOverview: false,
        });
      },

      closeOverview: () => {
        set({ showOverview: false });
      },

      openOverview: (page: string) => {
        set({
          showOverview: true,
          currentPage: page,
        });
      },

      hasCompletedPage: (page: string) => {
        return get().completedPages.includes(page);
      },

      syncWithUser: (userId: string) => {
        const { userId: storedUserId } = get();
        if (storedUserId !== userId) {
          set({ completedPages: [], userId });
        }
      },
    }),
    {
      name: STORAGE_KEY,
      partialize: (state) => ({ completedPages: state.completedPages, userId: state.userId }),
    }
  )
);

export const PAGE_CONFIGS: Record<string, PageConfig> = {
  home: {
    page: "home",
    overview:
      "Your financial dashboard shows a complete picture of your money. View balances, spending trends, and cash flow at a glance.",
    steps: [
      {
        id: "dashboard",
        title: "Views and Filters",
        content:
          "Use the controls above to customize your dashboard—select accounts, date ranges, and time periods. Your KPIs and charts below update automatically.",
        target: "walkthrough-filters",
      },
    ],
  },
  transactions: {
    page: "transactions",
    overview:
      "View, search, and manage all your transactions. Filter by account, category, or date. Edit categories inline.",
    steps: [
      { id: "search", title: "Search Bar", content: "Find transactions by description or amount.", target: "walkthrough-search" },
      { id: "filters", title: "Filters", content: "Filter by category, account, date range, or amount.", target: "walkthrough-filters" },
      { id: "table", title: "Transaction Table", content: "Sortable list of all transactions. Click a row for details.", target: "walkthrough-table" },
      { id: "category-badge", title: "Category Badge", content: "Click to reassign a transaction to a different category.", target: "walkthrough-category-badge" },
      { id: "import", title: "Import Button", content: "Upload CSV files from your bank to import transactions.", target: "walkthrough-import" },
    ],
  },
  subscriptions: {
    page: "subscriptions",
    overview:
      "Track recurring expenses like streaming services and bills. Syllogic auto-detects subscriptions from your transactions.",
    steps: [
      { id: "kpis", title: "Subscription KPIs", content: "Monthly and annual recurring costs at a glance.", target: "walkthrough-kpis" },
      { id: "list", title: "Subscription List", content: "All your active recurring expenses.", target: "walkthrough-list" },
      { id: "suggestions", title: "Smart Suggestions", content: "AI-detected potential subscriptions from your transactions.", target: "walkthrough-suggestions" },
      { id: "add", title: "Add Subscription", content: "Manually add subscriptions not detected automatically.", target: "walkthrough-add" },
    ],
  },
  assets: {
    page: "assets",
    overview:
      "Manage all financial assets including bank accounts, properties, and vehicles to track your net worth.",
    steps: [
      { id: "add", title: "Add Asset", content: "Add bank accounts, properties, or vehicles.", target: "walkthrough-add" },
      { id: "accounts", title: "Accounts Section", content: "Bank and investment accounts.", target: "walkthrough-accounts" },
      { id: "properties", title: "Properties Section", content: "Real estate holdings.", target: "walkthrough-properties" },
      { id: "vehicles", title: "Vehicles Section", content: "Vehicle values.", target: "walkthrough-vehicles" },
    ],
  },
  settings: {
    page: "settings",
    overview:
      "Customize your profile, manage spending categories, and configure integrations.",
    steps: [
      { id: "profile", title: "Profile Tab", content: "Update your name, email, and photo.", target: "walkthrough-profile" },
      { id: "categories", title: "Categories Tab", content: "Create and manage custom spending categories.", target: "walkthrough-categories" },
      { id: "api-keys", title: "API Keys Tab", content: "Generate API keys for integrations.", target: "walkthrough-api-keys" },
    ],
  },
};

export function getPageConfig(pathname: string): PageConfig | null {
  const routeMap: Record<string, string> = {
    "/": "home",
    "/transactions": "transactions",
    "/subscriptions": "subscriptions",
    "/assets": "assets",
    "/settings": "settings",
  };
  const pageKey = routeMap[pathname];
  return pageKey ? PAGE_CONFIGS[pageKey] ?? null : null;
}
