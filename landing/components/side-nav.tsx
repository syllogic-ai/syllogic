"use client";

import { useEffect, useState } from "react";
import { ScrambleText } from "./scramble-text";

const SECTIONS = [
  { id: "hero", label: "00" },
  { id: "signals", label: "01" },
  { id: "preview", label: "02" },
  { id: "why", label: "03" },
  { id: "work", label: "04" },
  { id: "install", label: "05" },
  { id: "roadmap", label: "06" },
  { id: "colophon", label: "07" },
  { id: "authors", label: "08" },
];

export function SideNav() {
  const [active, setActive] = useState("hero");

  useEffect(() => {
    const observers = SECTIONS.map(({ id }) => {
      const el = document.getElementById(id);
      if (!el) return null;

      const observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) setActive(id);
        },
        { threshold: 0.4, rootMargin: "-20% 0px -20% 0px" }
      );

      observer.observe(el);
      return observer;
    });

    return () => observers.forEach((o) => o?.disconnect());
  }, []);

  return (
    <nav className="fixed left-6 top-1/2 -translate-y-1/2 z-50 hidden lg:flex flex-col gap-5">
      {SECTIONS.map(({ id, label }) => (
        <a
          key={id}
          href={`#${id}`}
          className="flex items-center gap-2 group"
          style={{
            color: active === id ? "var(--color-accent)" : "var(--color-muted)",
          }}
        >
          <span
            className="block w-4 h-px transition-all duration-300"
            style={{
              backgroundColor:
                active === id ? "var(--color-accent)" : "var(--color-muted)",
              width: active === id ? "20px" : "12px",
            }}
          />
          <ScrambleText className="text-xs font-mono transition-colors duration-200 group-hover:text-fg">
            {label}
          </ScrambleText>
        </a>
      ))}
    </nav>
  );
}
