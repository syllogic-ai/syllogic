"use client";

import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { RiUserLine, RiFolderLine } from "@remixicon/react";
import { ProfileEditor } from "./profile-editor";
import { CategoryManager } from "./category-manager";
import type { User, Category } from "@/lib/db/schema";

interface SettingsTabsProps {
  user: User;
  categories: Category[];
}

export function SettingsTabs({ user, categories }: SettingsTabsProps) {
  return (
    <Tabs defaultValue="profile" className="flex-1">
      <TabsList variant="line" className="mb-6">
        <TabsTrigger value="profile">
          <RiUserLine className="mr-1.5 h-4 w-4" />
          Profile
        </TabsTrigger>
        <TabsTrigger value="categories">
          <RiFolderLine className="mr-1.5 h-4 w-4" />
          Categories
        </TabsTrigger>
      </TabsList>

      <TabsContent value="profile">
        <ProfileEditor user={user} />
      </TabsContent>

      <TabsContent value="categories">
        <CategoryManager initialCategories={categories} />
      </TabsContent>
    </Tabs>
  );
}
