"use client";

import { useMemo } from "react";
import { RiBankLine } from "@remixicon/react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";
import { withAssetVersion } from "@/lib/utils/asset-url";

interface AccountLogoProps {
  name: string;
  logoUrl?: string | null;
  updatedAt?: Date | string | number | null;
  size?: "sm" | "default" | "lg";
  className?: string;
}

export function AccountLogo({
  name,
  logoUrl,
  updatedAt,
  size = "default",
  className,
}: AccountLogoProps) {
  const resolvedLogoUrl = useMemo(
    () => withAssetVersion(logoUrl, updatedAt),
    [logoUrl, updatedAt]
  );

  return (
    <Avatar size={size} className={cn("shrink-0", className)}>
      {resolvedLogoUrl ? (
        <AvatarImage
          src={resolvedLogoUrl}
          alt={name}
          loading="eager"
          key={resolvedLogoUrl}
        />
      ) : null}
      <AvatarFallback className="bg-muted text-muted-foreground">
        <RiBankLine className="h-4 w-4" />
      </AvatarFallback>
    </Avatar>
  );
}
