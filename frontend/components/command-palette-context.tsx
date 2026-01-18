"use client";

import * as React from "react";

interface CommandPaletteCallbacks {
  onAddTransaction?: () => void;
  onExportCSV?: () => void;
  onAddAsset?: () => void;
  onRefreshData?: () => void;
}

interface CommandPaletteContextValue {
  callbacks: CommandPaletteCallbacks;
  registerCallbacks: (callbacks: Partial<CommandPaletteCallbacks>) => void;
  unregisterCallbacks: (keys: (keyof CommandPaletteCallbacks)[]) => void;
}

const CommandPaletteContext = React.createContext<CommandPaletteContextValue | null>(null);

export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  const [callbacks, setCallbacks] = React.useState<CommandPaletteCallbacks>({});

  const registerCallbacks = React.useCallback((newCallbacks: Partial<CommandPaletteCallbacks>) => {
    setCallbacks((prev) => ({ ...prev, ...newCallbacks }));
  }, []);

  const unregisterCallbacks = React.useCallback((keys: (keyof CommandPaletteCallbacks)[]) => {
    setCallbacks((prev) => {
      const next = { ...prev };
      keys.forEach((key) => {
        delete next[key];
      });
      return next;
    });
  }, []);

  return (
    <CommandPaletteContext.Provider value={{ callbacks, registerCallbacks, unregisterCallbacks }}>
      {children}
    </CommandPaletteContext.Provider>
  );
}

export function useCommandPaletteCallbacks() {
  const context = React.useContext(CommandPaletteContext);
  if (!context) {
    throw new Error("useCommandPaletteCallbacks must be used within a CommandPaletteProvider");
  }
  return context;
}

export function useRegisterCommandPaletteCallbacks(
  callbacks: Partial<CommandPaletteCallbacks>,
  deps: React.DependencyList
) {
  const { registerCallbacks, unregisterCallbacks } = useCommandPaletteCallbacks();

  React.useEffect(() => {
    registerCallbacks(callbacks);
    return () => {
      unregisterCallbacks(Object.keys(callbacks) as (keyof CommandPaletteCallbacks)[]);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}
