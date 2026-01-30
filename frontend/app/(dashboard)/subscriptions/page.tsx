import { Header } from "@/components/layout/header";
import { SubscriptionsClient } from "@/components/subscriptions/subscriptions-client";
import { getSubscriptions } from "@/lib/actions/subscriptions";
import { getUserCategories } from "@/lib/actions/categories";
import { getPendingSuggestions } from "@/lib/actions/subscription-suggestions";

export default async function SubscriptionsPage() {
  const [subscriptions, categories, suggestions] = await Promise.all([
    getSubscriptions(),
    getUserCategories(),
    getPendingSuggestions(),
  ]);

  return (
    <>
      <Header title="Subscriptions" />
      <div className="flex h-[calc(100vh-4rem)] flex-col gap-4 p-4 pt-0">
        <SubscriptionsClient
          initialSubscriptions={subscriptions}
          categories={categories}
          suggestions={suggestions}
        />
      </div>
    </>
  );
}
