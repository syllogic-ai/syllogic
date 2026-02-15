"use client";

import { useState } from "react";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { cn } from "@/lib/utils";

interface CompanyLogoProps {
  name: string;
  logoUrl?: string | null;
  size?: "sm" | "default" | "lg";
  className?: string;
}

/**
 * Generate a consistent color based on the company name
 */
function generateColor(name: string): string {
  // Predefined colors that work well as backgrounds
  const colors = [
    "#ef4444", // red
    "#f97316", // orange
    "#f59e0b", // amber
    "#eab308", // yellow
    "#84cc16", // lime
    "#22c55e", // green
    "#10b981", // emerald
    "#14b8a6", // teal
    "#06b6d4", // cyan
    "#0ea5e9", // sky
    "#3b82f6", // blue
    "#6366f1", // indigo
    "#8b5cf6", // violet
    "#a855f7", // purple
    "#d946ef", // fuchsia
    "#ec4899", // pink
    "#f43f5e", // rose
  ];

  // Generate a hash from the name
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
    hash = hash & hash; // Convert to 32bit integer
  }

  // Use the hash to pick a color
  const index = Math.abs(hash) % colors.length;
  return colors[index];
}

/**
 * Get initials from a company name (max 2 characters)
 */
function getInitials(name: string): string {
  const words = name.trim().split(/\s+/);

  if (words.length === 1) {
    // Single word: take first two characters
    return words[0].substring(0, 2).toUpperCase();
  }

  // Multiple words: take first character of first two words
  return words
    .slice(0, 2)
    .map((word) => word.charAt(0))
    .join("")
    .toUpperCase();
}

export function CompanyLogo({
  name,
  logoUrl,
  size = "default",
  className,
}: CompanyLogoProps) {
  const [status, setStatus] = useState<"empty" | "loading" | "loaded" | "error">(() =>
    logoUrl ? "loading" : "empty"
  );

  const initials = getInitials(name);
  const bgColor = generateColor(name);

  const showInitialsFallback = !logoUrl || status === "error";

  return (
    <Avatar size={size} className={cn("shrink-0", className)}>
      {logoUrl ? (
        <AvatarImage
          src={logoUrl}
          alt={name}
          loading="eager"
          key={logoUrl}
          onLoad={() => setStatus("loaded")}
          onError={() => setStatus("error")}
        />
      ) : null}
      <AvatarFallback
        style={
          showInitialsFallback
            ? { backgroundColor: bgColor, color: "white" }
            : undefined
        }
        className={cn(showInitialsFallback ? "" : "bg-muted text-muted-foreground")}
      >
        {showInitialsFallback ? (
          initials
        ) : (
          <span className="block size-full animate-pulse bg-muted" />
        )}
      </AvatarFallback>
    </Avatar>
  );
}
