"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export interface Feature {
  id: string;
  title: string;
  description: string;
  detail: string;
  wide?: boolean;
  useCases?: string[];
}

interface FeatureModalProps {
  feature: Feature;
  onClose: () => void;
}

export function FeatureModal({ feature, onClose }: FeatureModalProps) {
  const [mounted, setMounted] = useState(false);
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMounted(true);

    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!mounted) return null;

  return createPortal(
    // Overlay is the scroll container — click outside inner panel closes it
    <div
      ref={overlayRef}
      className="fixed inset-0 z-[200] overflow-y-auto py-12 px-4 md:px-8"
      style={{
        backgroundColor: "rgba(5,5,5,0.88)",
        backdropFilter: "blur(6px)",
      }}
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
    >
      <div
        className="relative w-full max-w-2xl mx-auto"
        style={{
          backgroundColor: "#0c0c0c",
          border: "1px solid var(--color-border)",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-6 py-4"
          style={{ borderBottom: "1px solid var(--color-border)" }}
        >
          <div className="flex items-center gap-3">
            <span
              className="font-mono text-xs"
              style={{ color: "var(--color-accent)" }}
            >
              {feature.id}
            </span>
            <h2
              className="font-display text-2xl"
              style={{ color: "var(--color-fg)" }}
            >
              {feature.title.toUpperCase()}
            </h2>
          </div>
          <button
            onClick={onClose}
            className="font-mono text-2xl leading-none w-8 h-8 flex items-center justify-center transition-colors"
            style={{ color: "var(--color-muted)" }}
            onMouseEnter={(e) =>
              ((e.currentTarget as HTMLElement).style.color =
                "var(--color-fg)")
            }
            onMouseLeave={(e) =>
              ((e.currentTarget as HTMLElement).style.color =
                "var(--color-muted)")
            }
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {/* Screenshot placeholder */}
        <div
          className="w-full flex flex-col items-center justify-center gap-3"
          style={{
            height: "240px",
            backgroundColor: "rgba(255,255,255,0.015)",
            borderBottom: "1px solid var(--color-border)",
          }}
        >
          <div
            className="grid grid-cols-3 gap-1 opacity-20"
            style={{ width: 48 }}
          >
            {Array.from({ length: 9 }).map((_, i) => (
              <div
                key={i}
                className="h-1"
                style={{ backgroundColor: "var(--color-accent)" }}
              />
            ))}
          </div>
          <span
            className="font-mono text-xs uppercase tracking-[0.2em]"
            style={{ color: "var(--color-muted)" }}
          >
            Screenshot · {feature.title}
          </span>
          <span
            className="font-mono text-xs"
            style={{ color: "rgba(90,90,90,0.6)" }}
          >
            Add image here
          </span>
        </div>

        {/* Body */}
        <div className="p-6 space-y-6">
          <p
            className="font-mono text-sm leading-relaxed"
            style={{ color: "rgba(232,230,225,0.8)" }}
          >
            {feature.detail}
          </p>

          {feature.useCases && feature.useCases.length > 0 && (
            <div>
              <p
                className="font-mono text-xs uppercase tracking-widest mb-4"
                style={{ color: "var(--color-muted)" }}
              >
                Example prompts
              </p>
              <ul className="space-y-2">
                {feature.useCases.map((uc, i) => (
                  <li
                    key={i}
                    className="font-mono text-sm leading-relaxed"
                    style={{
                      color: "rgba(232,230,225,0.7)",
                      borderLeft: "2px solid var(--color-accent)",
                      paddingLeft: "12px",
                    }}
                  >
                    {uc}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
