import { SubscriptionsClient } from "@/components/subscriptions/subscriptions-client";
import { getSubscriptions, getSubscriptionKpis } from "@/lib/actions/subscriptions";
import { getUserCategories } from "@/lib/actions/categories";
import { getPendingSuggestions } from "@/lib/actions/subscription-suggestions";

export default async function SubscriptionsPage() {
  const [subscriptions, categories, suggestions, kpis] = await Promise.all([
    getSubscriptions(),
    getUserCategories(),
    getPendingSuggestions(),
    getSubscriptionKpis(),
  ]);

  return (
    <div className="flex min-h-[calc(100vh-4rem)] flex-col gap-4 p-4">
      <SubscriptionsClient
        initialSubscriptions={subscriptions}
        categories={categories}
        suggestions={suggestions}
        kpis={kpis}
      />
    </div>
  );
}
