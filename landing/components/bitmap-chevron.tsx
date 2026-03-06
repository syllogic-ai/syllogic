import { cn } from "@/lib/utils";
import type { CSSProperties } from "react";

interface BitmapChevronProps {
  className?: string;
  size?: number;
  style?: CSSProperties;
}

export function BitmapChevron({ className, size = 10, style }: BitmapChevronProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 10 10"
      fill="none"
      className={cn("inline-block shrink-0", className)}
      style={style}
    >
      <path
        d="M1 3L5 7L9 3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="square"
        strokeLinejoin="miter"
      />
    </svg>
  );
}
