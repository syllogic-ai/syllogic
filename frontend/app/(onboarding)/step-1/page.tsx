"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import { RiArrowRightLine, RiLoader4Line } from "@remixicon/react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { OnboardingProgress } from "@/components/onboarding/onboarding-progress";
import { ProfilePhotoUpload } from "@/components/onboarding/profile-photo-upload";
import { CurrencySelector } from "@/components/onboarding/currency-selector";
import { updatePersonalDetails, getCurrentUser } from "@/lib/actions/onboarding";
import { useEffect } from "react";

export default function OnboardingStep1Page() {
  const router = useRouter();
  const [isPending, startTransition] = useTransition();
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [profilePhoto, setProfilePhoto] = useState<File | null>(null);
  const [defaultImage, setDefaultImage] = useState<string | null>(null);

  // Load current user data on mount
  useEffect(() => {
    async function loadUser() {
      const user = await getCurrentUser();
      if (user) {
        setName(user.name || "");
        setCurrency(user.functionalCurrency || "EUR");
        setDefaultImage(user.profilePhotoPath || user.image || null);
      }
    }
    loadUser();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      toast.error("Please enter your name");
      return;
    }

    startTransition(async () => {
      const formData = new FormData();
      formData.append("name", name);
      formData.append("currency", currency);
      if (profilePhoto) {
        formData.append("profilePhoto", profilePhoto);
      }

      const result = await updatePersonalDetails(formData);

      if (result.success) {
        router.push("/step-2");
      } else {
        toast.error(result.error || "Failed to save profile");
      }
    });
  };

  return (
    <div className="space-y-8">
      <OnboardingProgress currentStep={1} />

      <Card>
        <CardHeader>
          <CardTitle>Welcome! Let&apos;s set up your profile</CardTitle>
          <CardDescription>
            Tell us a bit about yourself to personalize your experience.
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-6">
            <div className="flex flex-col items-center gap-4">
              <Label className="text-center">Profile Photo</Label>
              <ProfilePhotoUpload
                value={profilePhoto}
                onChange={setProfilePhoto}
                defaultImage={defaultImage}
                name={name}
              />
              <p className="text-xs text-muted-foreground text-center">
                Click or drag to upload a profile photo (optional)
              </p>
            </div>

            <div className="space-y-2">
              <Label htmlFor="name">Your Name *</Label>
              <Input
                id="name"
                placeholder="Enter your name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>

            <CurrencySelector
              value={currency}
              onChange={setCurrency}
              label="Functional Currency"
              showTooltip={true}
            />
          </CardContent>
          <CardFooter className="flex justify-end">
            <Button type="submit" disabled={isPending || !name.trim()}>
              {isPending ? (
                <>
                  <RiLoader4Line className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  Continue
                  <RiArrowRightLine className="ml-2 h-4 w-4" />
                </>
              )}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
