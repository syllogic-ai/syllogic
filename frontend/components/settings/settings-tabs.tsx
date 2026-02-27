"use client";

import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { RiUserLine, RiFolderLine, RiKeyLine } from "@remixicon/react";
import { ProfileEditor } from "./profile-editor";
import { CategoryManager } from "./category-manager";
import { ApiKeysManager } from "./api-keys-manager";
import type { User, Category } from "@/lib/db/schema";

interface SettingsTabsProps {
  user: User;
  categories: Category[];
  apiKeys: Array<{
    id: string;
    name: string;
    keyPrefix: string;
    lastUsedAt: Date | null;
    expiresAt: Date | null;
    createdAt: Date | null;
  }>;
}

export function SettingsTabs({ user, categories, apiKeys }: SettingsTabsProps) {
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
      </TabsList>

      <TabsContent value="profile">
        <ProfileEditor user={user} />
      </TabsContent>

      <TabsContent value="categories">
        <CategoryManager initialCategories={categories} />
      </TabsContent>

      <TabsContent value="api-keys">
        <ApiKeysManager initialKeys={apiKeys} />
      </TabsContent>
    </Tabs>
  );
}
