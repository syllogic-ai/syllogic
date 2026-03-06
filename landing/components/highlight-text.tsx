"use client";

import { useEffect, useRef, useState } from "react";

interface HighlightTextProps {
  children: string;
  className?: string;
}

export function HighlightText({ children, className }: HighlightTextProps) {
  const ref = useRef<HTMLSpanElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.5 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <span ref={ref} className={`relative inline ${className ?? ""}`}>
      <span
        className="absolute inset-y-0 left-0 bg-accent/20 origin-left transition-all duration-700 ease-out"
        style={{
          width: visible ? "100%" : "0%",
        }}
      />
      <span className="relative">{children}</span>
    </span>
  );
}
