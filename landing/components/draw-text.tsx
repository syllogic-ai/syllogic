"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

interface DrawTextProps {
  children: string;
  className?: string;
}

export function DrawText({ children, className }: DrawTextProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setRevealed(true);
          observer.disconnect();
        }
      },
      { threshold: 0.3 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <span
      ref={ref}
      className={cn(
        "relative inline-block overflow-hidden",
        className
      )}
    >
      <span
        className="block transition-transform duration-700 ease-out"
        style={{ transform: revealed ? "translateY(0%)" : "translateY(110%)" }}
      >
        {children}
      </span>
    </span>
  );
}
