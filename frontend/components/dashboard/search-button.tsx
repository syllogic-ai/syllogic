"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";

export function SearchButton() {
  const handleClick = React.useCallback(() => {
    // Dispatch keyboard event to trigger command palette
    const event = new KeyboardEvent("keydown", {
      key: "k",
      code: "KeyK",
      metaKey: true,
      bubbles: true,
    });
    document.dispatchEvent(event);
  }, []);

  return (
    <Button
      variant="outline"
      className="h-9 w-[200px] justify-between px-3 bg-transparent"
      onClick={handleClick}
    >
      <span className="text-xs text-muted-foreground">Search...</span>
      <kbd className="pointer-events-none ml-1 hidden h-5 select-none items-center gap-0.5 border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-100 sm:flex">
        <span className="text-xs">⌘</span>K
      </kbd>
    </Button>
  );
}
