"use client";

import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { RiUserLine, RiFolderLine, RiKeyLine, RiUploadLine } from "@remixicon/react";
import { ProfileEditor } from "./profile-editor";
import { CategoryManager } from "./category-manager";
import { ApiKeysManager } from "./api-keys-manager";
import { ImportHistoryManager } from "./import-history-manager";
import type { User, Category } from "@/lib/db/schema";
import type { CsvImportWithStats } from "@/lib/actions/csv-import";

interface SettingsTabsProps {
  user: User;
  categories: Category[];
  mcpServerUrl: string;
  canCreateApiKeys: boolean;
  canDelete?: boolean;
  apiKeys: Array<{
    id: string;
    name: string;
    keyPrefix: string;
    lastUsedAt: Date | null;
    expiresAt: Date | null;
    createdAt: Date | null;
  }>;
  csvImports: CsvImportWithStats[];
}

export function SettingsTabs({
  user,
  categories,
  apiKeys,
  mcpServerUrl,
  canCreateApiKeys,
  canDelete = true,
  csvImports,
}: SettingsTabsProps) {
  return (
    <Tabs defaultValue="profile" className="flex-1">
      <TabsList variant="line" className="mb-6">
        <TabsTrigger value="profile" data-walkthrough="walkthrough-profile">
          <RiUserLine className="mr-1.5 h-4 w-4" />
          Profile
        </TabsTrigger>
        <TabsTrigger value="categories" data-walkthrough="walkthrough-categories">
          <RiFolderLine className="mr-1.5 h-4 w-4" />
          Categories
        </TabsTrigger>
        <TabsTrigger value="api-keys" data-walkthrough="walkthrough-api-keys">
          <RiKeyLine className="mr-1.5 h-4 w-4" />
          API Keys
        </TabsTrigger>
        <TabsTrigger value="import-history" data-walkthrough="walkthrough-import-history">
          <RiUploadLine className="mr-1.5 h-4 w-4" />
          Import History
        </TabsTrigger>
      </TabsList>

      <TabsContent value="profile">
        <ProfileEditor user={user} />
      </TabsContent>

      <TabsContent value="categories">
        <CategoryManager initialCategories={categories} />
      </TabsContent>

      <TabsContent value="api-keys">
        <ApiKeysManager
          initialKeys={apiKeys}
          mcpServerUrl={mcpServerUrl}
          canCreateApiKeys={canCreateApiKeys}
        />
      </TabsContent>

      <TabsContent value="import-history">
        <ImportHistoryManager initialImports={csvImports} canDelete={canDelete} />
      </TabsContent>
    </Tabs>
  );
}
