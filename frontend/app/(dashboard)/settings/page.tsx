import { redirect } from "next/navigation";
import { Header } from "@/components/layout/header";
import { SettingsTabs } from "@/components/settings/settings-tabs";
import { getCurrentUserProfile } from "@/lib/actions/settings";
import { getCategories } from "@/lib/actions/categories";
import { listApiKeys } from "@/lib/actions/api-keys";
import { resolveMcpServerUrlForSnippet } from "@/lib/mcp/server-url";

export default async function SettingsPage() {
  const user = await getCurrentUserProfile();

  if (!user) {
    redirect("/login");
  }

  const [categories, apiKeysResult] = await Promise.all([
    getCategories(),
    listApiKeys(),
  ]);

  const apiKeys = apiKeysResult.success && apiKeysResult.keys ? apiKeysResult.keys : [];
  const mcpServerUrl = resolveMcpServerUrlForSnippet({
    mcpServerUrl: process.env.MCP_SERVER_URL,
    betterAuthUrl: process.env.BETTER_AUTH_URL || process.env.NEXT_PUBLIC_BETTER_AUTH_URL,
    appUrl: process.env.APP_URL,
  });

  return (
    <>
      <Header title="Settings" />
      <div className="flex flex-1 flex-col p-4 pt-0">
        <SettingsTabs
          user={user}
          categories={categories}
          apiKeys={apiKeys}
          mcpServerUrl={mcpServerUrl}
        />
      </div>
    </>
  );
}
