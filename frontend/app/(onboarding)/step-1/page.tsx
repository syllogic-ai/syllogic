"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { RiArrowRightLine } from "@remixicon/react";
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
import { OnboardingProgress } from "@/components/onboarding/onboarding-progress";
import { ProfilePhotoUpload } from "@/components/onboarding/profile-photo-upload";
import { CurrencySelector } from "@/components/onboarding/currency-selector";
import { updatePersonalDetails } from "@/lib/actions/onboarding";

export default function Step1Page() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("EUR");
  const [profilePhoto, setProfilePhoto] = useState<File | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      toast.error("Please enter your name");
      return;
    }

    setIsLoading(true);

    try {
      const formData = new FormData();
      formData.append("name", name.trim());
      formData.append("functionalCurrency", currency);
      if (profilePhoto) {
        formData.append("profilePhoto", profilePhoto);
      }

      const result = await updatePersonalDetails(formData);

      if (result.success) {
        toast.success("Personal details saved");
        router.push("/step-2");
      } else {
        toast.error(result.error || "Failed to save personal details");
      }
    } catch {
      toast.error("An error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-8">
      <OnboardingProgress currentStep={1} />

      <Card>
        <CardHeader>
          <CardTitle>Welcome! Let's set up your profile</CardTitle>
          <CardDescription>
            Tell us a bit about yourself to personalize your experience.
          </CardDescription>
        </CardHeader>
        <form onSubmit={handleSubmit}>
          <CardContent className="space-y-6">
            <ProfilePhotoUpload
              value={profilePhoto}
              onChange={setProfilePhoto}
              name={name}
            />

            <div className="space-y-2">
              <Label htmlFor="name">Full Name</Label>
              <Input
                id="name"
                placeholder="Enter your full name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
            </div>

            <CurrencySelector value={currency} onChange={setCurrency} />
          </CardContent>
          <CardFooter className="justify-end">
            <Button type="submit" disabled={isLoading}>
              {isLoading ? "Saving..." : "Continue"}
              <RiArrowRightLine className="ml-2 h-4 w-4" />
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
