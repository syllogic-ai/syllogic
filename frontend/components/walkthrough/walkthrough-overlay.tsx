"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import { useWalkthroughStore, type WalkthroughStep } from "./walkthrough-store";

interface WalkthroughOverlayProps {
  step: WalkthroughStep | null;
}

export function WalkthroughOverlay({ step }: WalkthroughOverlayProps) {
  const [targetRect, setTargetRect] = useState<DOMRect | null>(null);
  const [padding, setPadding] = useState(8);

  const updateTargetRect = useCallback(() => {
    if (!step?.target) {
      setTargetRect(null);
      return;
    }
    const el = document.querySelector(`[data-walkthrough="${step.target}"]`);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      requestAnimationFrame(() => {
        const rect = el.getBoundingClientRect();
        setTargetRect(rect);
      });
    } else {
      setTargetRect(null);
    }
  }, [step?.target]);

  useEffect(() => {
    updateTargetRect();
    const resizeObserver = new ResizeObserver(updateTargetRect);
    const el = step?.target
      ? document.querySelector(`[data-walkthrough="${step.target}"]`)
      : null;
    if (el) resizeObserver.observe(el);

    window.addEventListener("resize", updateTargetRect);
    window.addEventListener("scroll", updateTargetRect, true);

    return () => {
      resizeObserver.disconnect();
      window.removeEventListener("resize", updateTargetRect);
      window.removeEventListener("scroll", updateTargetRect, true);
    };
  }, [step?.target, updateTargetRect]);

  if (!step) return null;

  return (
    <AnimatePresence>
      <motion.div
        key={step.id}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[9998] pointer-events-none"
        aria-hidden
      >
        {/* Backdrop with cutout */}
        <svg
          className="absolute inset-0 w-full h-full pointer-events-auto"
          style={{ isolation: "isolate" }}
        >
          <defs>
            <mask id="walkthrough-mask">
              <rect width="100%" height="100%" fill="white" />
              {targetRect && (
                <rect
                  x={targetRect.left - padding}
                  y={targetRect.top - padding}
                  width={targetRect.width + padding * 2}
                  height={targetRect.height + padding * 2}
                  rx="2"
                  fill="black"
                />
              )}
            </mask>
          </defs>
          <rect
            width="100%"
            height="100%"
            fill="rgba(0,0,0,0.6)"
            mask="url(#walkthrough-mask)"
          />
        </svg>
      </motion.div>
    </AnimatePresence>
  );
}
