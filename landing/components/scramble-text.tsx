"use client";

import { useState, useRef, useCallback } from "react";

const SCRAMBLE_CHARS = "!<>-_\\/[]{}—=+*^?#@";

interface ScrambleTextProps {
  children: string;
  className?: string;
}

export function ScrambleText({ children, className }: ScrambleTextProps) {
  const [display, setDisplay] = useState(children);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const scramble = useCallback(() => {
    const original = children;
    let iteration = 0;

    if (intervalRef.current) clearInterval(intervalRef.current);

    intervalRef.current = setInterval(() => {
      setDisplay(
        original
          .split("")
          .map((char, i) => {
            if (i < iteration) return original[i];
            return SCRAMBLE_CHARS[
              Math.floor(Math.random() * SCRAMBLE_CHARS.length)
            ];
          })
          .join("")
      );

      if (iteration >= original.length) {
        if (intervalRef.current) clearInterval(intervalRef.current);
        setDisplay(original);
      }

      iteration += 1 / 3;
    }, 28);
  }, [children]);

  return (
    <span className={className} onMouseEnter={scramble}>
      {display}
    </span>
  );
}
