import { redirect } from "next/navigation";
import { Header } from "@/components/layout/header";
import { SettingsTabs } from "@/components/settings/settings-tabs";
import { getCurrentUserProfile } from "@/lib/actions/settings";
import { getCategories } from "@/lib/actions/categories";

export default async function SettingsPage() {
  const user = await getCurrentUserProfile();

  if (!user) {
    redirect("/login");
  }

  const categories = await getCategories();

  return (
    <>
      <Header title="Settings" />
      <div className="flex flex-1 flex-col p-4 pt-0">
        <SettingsTabs user={user} categories={categories} />
      </div>
    </>
  );
}
