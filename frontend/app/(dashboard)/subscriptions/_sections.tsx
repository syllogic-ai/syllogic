import { SubscriptionsClient } from "@/components/subscriptions/subscriptions-client";
import { getSubscriptions, getSubscriptionKpis } from "@/lib/actions/subscriptions";
import { getUserCategories } from "@/lib/actions/categories";
import { getPendingSuggestions } from "@/lib/actions/subscription-suggestions";
import { getAccounts } from "@/lib/actions/accounts";

export async function SubscriptionsSection() {
  const [subscriptions, accounts, categories, suggestions, kpis] = await Promise.all([
    getSubscriptions(),
    getAccounts(),
    getUserCategories(),
    getPendingSuggestions(),
    getSubscriptionKpis(),
  ]);

  return (
    <SubscriptionsClient
      initialSubscriptions={subscriptions}
      accounts={accounts}
      categories={categories}
      suggestions={suggestions}
      kpis={kpis}
    />
  );
}
