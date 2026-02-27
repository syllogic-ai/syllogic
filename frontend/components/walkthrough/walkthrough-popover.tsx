"use client";

import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import { RiArrowLeftLine, RiArrowRightLine, RiCloseLine } from "@remixicon/react";
import { Button } from "@/components/ui/button";
import {
  useWalkthroughStore,
  PAGE_CONFIGS,
  type WalkthroughStep,
} from "./walkthrough-store";

interface WalkthroughPopoverProps {
  step: WalkthroughStep | null;
}

export function WalkthroughPopover({ step }: WalkthroughPopoverProps) {
  const [position, setPosition] = useState<{ top: number; left: number } | null>(null);
  const { currentPage, currentStepIndex, nextStep, previousStep, skipWalkthrough } =
    useWalkthroughStore();

  const updatePosition = useCallback(() => {
    if (!step?.target) {
      setPosition(null);
      return;
    }
    const el = document.querySelector(`[data-walkthrough="${step.target}"]`);
    if (el) {
      const rect = el.getBoundingClientRect();
      const popoverWidth = 320;
      const popoverHeight = 180;
      const gap = 12;

      let top = rect.bottom + gap;
      let left = rect.left + rect.width / 2 - popoverWidth / 2;

      if (top + popoverHeight > window.innerHeight - 20) {
        top = rect.top - popoverHeight - gap;
      }
      if (top < 20) top = 20;
      if (left < 20) left = 20;
      if (left + popoverWidth > window.innerWidth - 20) {
        left = window.innerWidth - popoverWidth - 20;
      }

      setPosition({ top, left });
    } else {
      setPosition(null);
    }
  }, [step?.target]);

  useEffect(() => {
    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);

    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [step?.target, updatePosition]);

  if (!step || !currentPage) return null;

  const config = PAGE_CONFIGS[currentPage as keyof typeof PAGE_CONFIGS];
  const steps = config?.steps ?? [];
  const isFirst = currentStepIndex === 0;
  const isLast = currentStepIndex >= steps.length - 1;

  const content = (
    <motion.div
      key={step.id}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      className="fixed z-[9999] w-80 rounded-none border border-border bg-popover p-4 shadow-lg"
      style={
        position
          ? { top: position.top, left: position.left }
          : { top: "50%", left: "50%", transform: "translate(-50%, -50%)" }
      }
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <h3 className="font-medium text-sm">{step.title}</h3>
          <p className="text-muted-foreground text-xs mt-1">{step.content}</p>
          <p className="text-muted-foreground text-[10px] mt-2 opacity-80">
            Tip: Restart anytime from the Help (ⓘ) button in the sidebar.
          </p>
        </div>
        <Button
          variant="ghost"
          size="icon-xs"
          onClick={skipWalkthrough}
          aria-label="Close walkthrough"
          className="shrink-0"
        >
          <RiCloseLine className="size-4" />
        </Button>
      </div>
      <div className="flex items-center justify-between mt-4 gap-2">
        <span className="text-xs text-muted-foreground">
          {currentStepIndex + 1} of {steps.length}
        </span>
        <div className="flex gap-1">
          <Button
            variant="outline"
            size="sm"
            onClick={previousStep}
            disabled={isFirst}
          >
            <RiArrowLeftLine className="size-4" />
            Back
          </Button>
          <Button size="sm" onClick={nextStep}>
            {isLast ? "Finish" : "Next"}
            <RiArrowRightLine className="size-4" />
          </Button>
        </div>
      </div>
    </motion.div>
  );

  return <AnimatePresence mode="wait">{content}</AnimatePresence>;
}
