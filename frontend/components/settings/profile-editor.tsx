"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ProfilePhotoUpload } from "@/components/onboarding/profile-photo-upload";
import { DemoReadOnlyNotice } from "@/components/settings/demo-readonly-notice";
import { updateUserProfile } from "@/lib/actions/settings";
import type { User } from "@/lib/db/schema";

interface ProfileEditorProps {
  user: User;
  isDemoUser?: boolean;
}

export function ProfileEditor({ user, isDemoUser = false }: ProfileEditorProps) {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [name, setName] = useState(user.name || "");
  const [profilePhoto, setProfilePhoto] = useState<File | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (isDemoUser) return;

    if (!name.trim()) {
      toast.error("Please enter your name");
      return;
    }

    setIsLoading(true);

    try {
      const formData = new FormData();
      formData.append("name", name.trim());
      if (profilePhoto) {
        formData.append("profilePhoto", profilePhoto);
      }

      const result = await updateUserProfile(formData);

      if (result.success) {
        toast.success("Profile updated successfully");
        setProfilePhoto(null);
        router.refresh();
      } else {
        toast.error(result.error || "Failed to update profile");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Profile</CardTitle>
        <CardDescription>
          Update your personal information and preferences.
        </CardDescription>
      </CardHeader>
      <form onSubmit={handleSubmit}>
        <CardContent className="space-y-6 pb-6">
          {isDemoUser && <DemoReadOnlyNotice />}
          <ProfilePhotoUpload
            value={profilePhoto}
            onChange={setProfilePhoto}
            defaultImage={user.profilePhotoPath || user.image}
            name={name}
            disabled={isDemoUser}
          />

          <div className="space-y-2">
            <Label htmlFor="name">Name</Label>
            <Input
              id="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Your name"
              className="w-fit min-w-[200px]"
              disabled={isDemoUser}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              value={user.email}
              disabled
              className="w-fit min-w-[200px] bg-muted"
            />
            <p className="text-xs text-muted-foreground">
              Email cannot be changed.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="currency">Functional Currency</Label>
            <Input
              id="currency"
              value={user.functionalCurrency || "EUR"}
              disabled
              className="w-fit min-w-[80px] bg-muted"
            />
            <p className="text-xs text-muted-foreground">
              Functional currency is set during onboarding and cannot be changed.
            </p>
          </div>
        </CardContent>
        <CardFooter>
          <Button type="submit" disabled={isLoading || isDemoUser}>
            {isLoading ? "Saving..." : "Save Changes"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}
