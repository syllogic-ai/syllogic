"use client";

import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { RiUserLine, RiFolderLine, RiDatabase2Line } from "@remixicon/react";
import { ProfileEditor } from "./profile-editor";
import { CategoryManager } from "./category-manager";
import { ResetOnboardingDialog } from "./reset-onboarding-dialog";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
        <TabsTrigger value="data">
          <RiDatabase2Line className="mr-1.5 h-4 w-4" />
          Data
        </TabsTrigger>
      </TabsList>

      <TabsContent value="profile">
        <ProfileEditor user={user} />
      </TabsContent>

      <TabsContent value="categories">
        <CategoryManager initialCategories={categories} />
      </TabsContent>

      <TabsContent value="data">
        <Card>
          <CardHeader>
            <CardTitle>Data Management</CardTitle>
            <CardDescription>
              Manage your data and reset settings.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <h4 className="text-sm font-medium mb-1">Reset Onboarding</h4>
              <p className="text-sm text-muted-foreground mb-3">
                Start fresh with the onboarding process. This will delete all your categories
                and let you set them up again. Your accounts and transactions will not be affected.
              </p>
              <ResetOnboardingDialog />
            </div>
          </CardContent>
        </Card>
      </TabsContent>
    </Tabs>
  );
}
