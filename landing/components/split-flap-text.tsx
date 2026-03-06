"use client";

import { useEffect, useState } from "react";

const CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";

function SplitFlapChar({
  target,
  delay = 0,
}: {
  target: string;
  delay?: number;
}) {
  const [display, setDisplay] = useState("\u00A0");
  const [settled, setSettled] = useState(false);

  useEffect(() => {
    if (target === " ") {
      setDisplay("\u00A0");
      return;
    }

    const timeout = setTimeout(() => {
      let count = 0;
      const total = 10;
      const interval = setInterval(() => {
        if (count >= total) {
          setDisplay(target);
          setSettled(true);
          clearInterval(interval);
        } else {
          setDisplay(CHARS[Math.floor(Math.random() * CHARS.length)]);
          count++;
        }
      }, 55);

      return () => clearInterval(interval);
    }, delay);

    return () => clearTimeout(timeout);
  }, [target, delay]);

  return (
    <span
      className="inline-block transition-colors duration-100"
      style={{ color: settled ? "var(--color-fg)" : "var(--color-accent)" }}
    >
      {display}
    </span>
  );
}

interface SplitFlapTextProps {
  text: string;
  className?: string;
  startDelay?: number;
  charDelay?: number;
}

export function SplitFlapText({
  text,
  className,
  startDelay = 0,
  charDelay = 90,
}: SplitFlapTextProps) {
  return (
    <span className={className}>
      {text.split("").map((char, i) => (
        <SplitFlapChar
          key={i}
          target={char}
          delay={startDelay + i * charDelay}
        />
      ))}
    </span>
  );
}
