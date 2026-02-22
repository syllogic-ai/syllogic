"use client";

import * as React from "react";
import { useRouter, usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import {
  RiHomeLine,
  RiExchangeLine,
  RiSettings3Line,
  RiLoopRightLine,
  RiAddLine,
  RiMoonLine,
  RiSunLine,
  RiWallet3Line,
  RiDownloadLine,
  RiUploadLine,
  RiRefreshLine,
  RiLoader4Line,
} from "@remixicon/react";
import {
  CommandDialog,
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandShortcut,
  CommandSeparator,
} from "@/components/ui/command";
import {
  getCommandPaletteData,
  searchCommandPaletteTransactions,
  type CommandPaletteData,
} from "@/lib/actions/command-palette";
import { formatAmount, formatDate } from "@/lib/utils";
import { AccountLogo } from "@/components/ui/account-logo";
import { useCommandPaletteCallbacks } from "./command-palette-context";
import {
  GLOBAL_FILTER_STORAGE_KEY,
  resolveGlobalFilterQueryString,
} from "@/lib/filters/global-filters";

const MIN_SEARCH_LENGTH = 2;

export function CommandPalette() {
  const { callbacks } = useCommandPaletteCallbacks();
  const { onAddTransaction, onExportCSV, onAddAsset, onRefreshData } = callbacks;
  const [open, setOpen] = React.useState(false);
  const [data, setData] = React.useState<CommandPaletteData | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [isSearchingTransactions, setIsSearchingTransactions] = React.useState(false);
  const [transactionSearchResults, setTransactionSearchResults] = React.useState<
    CommandPaletteData["transactions"]
  >([]);
  const [search, setSearch] = React.useState("");
  const transactionSearchRequestIdRef = React.useRef(0);
  const router = useRouter();
  const pathname = usePathname();
  const { setTheme, theme } = useTheme();

  const getSharedFilterQueryString = React.useCallback(() => {
    if (typeof window === "undefined") {
      return "";
    }

    let storedQuery: string | null = null;
    try {
      storedQuery = localStorage.getItem(GLOBAL_FILTER_STORAGE_KEY);
    } catch {
      storedQuery = null;
    }

    return resolveGlobalFilterQueryString(window.location.search, storedQuery);
  }, []);

  const getHomePathWithFilters = React.useCallback(() => {
    const queryString = getSharedFilterQueryString();
    return queryString ? `/?${queryString}` : "/";
  }, [getSharedFilterQueryString]);

  const getTransactionsPathWithFilters = React.useCallback(() => {
    const queryString = getSharedFilterQueryString();
    return queryString ? `/transactions?${queryString}` : "/transactions";
  }, [getSharedFilterQueryString]);

  // Fetch data when search reaches minimum length
  React.useEffect(() => {
    if (open && search.length >= MIN_SEARCH_LENGTH && !data) {
      setIsLoading(true);
      getCommandPaletteData()
        .then(setData)
        .finally(() => setIsLoading(false));
    }
  }, [open, search, data]);

  // Reset search when palette closes
  React.useEffect(() => {
    if (!open) {
      setSearch("");
      setTransactionSearchResults([]);
      setIsSearchingTransactions(false);
    }
  }, [open]);

  // Handle Cmd+K to open palette
  React.useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener("keydown", down);
    return () => document.removeEventListener("keydown", down);
  }, []);

  // Handle direct navigation keys (only when palette is closed and not in input)
  React.useEffect(() => {
    const handleDirectKeys = (e: KeyboardEvent) => {
      // Skip if palette is open
      if (open) return;

      // Skip if modifier keys are pressed
      if (e.metaKey || e.ctrlKey || e.altKey || e.shiftKey) return;

      // Skip if focused on input/textarea/contenteditable
      const activeElement = document.activeElement;
      const isInputFocused =
        activeElement instanceof HTMLInputElement ||
        activeElement instanceof HTMLTextAreaElement ||
        activeElement?.getAttribute("contenteditable") === "true" ||
        activeElement?.closest("[cmdk-input]");

      if (isInputFocused) return;

      const key = e.key.toLowerCase();

      switch (key) {
        case "b":
          e.preventDefault();
          router.push(getHomePathWithFilters());
          break;
        case "t":
          e.preventDefault();
          router.push(getTransactionsPathWithFilters());
          break;
        case "a":
          e.preventDefault();
          router.push("/assets");
          break;
        case "s":
          e.preventDefault();
          router.push("/subscriptions");
          break;
        case "d":
          e.preventDefault();
          router.push("/settings");
          break;
        case "n":
          e.preventDefault();
          onAddTransaction?.();
          break;
        case "m":
          e.preventDefault();
          setTheme(theme === "dark" ? "light" : "dark");
          break;
      }
    };

    document.addEventListener("keydown", handleDirectKeys);
    return () => document.removeEventListener("keydown", handleDirectKeys);
  }, [open, router, theme, setTheme, onAddTransaction, getHomePathWithFilters, getTransactionsPathWithFilters]);

  const runCommand = React.useCallback((command: () => void) => {
    setOpen(false);
    command();
  }, []);

  // Default refresh handler
  const handleRefreshData = React.useCallback(() => {
    if (onRefreshData) {
      onRefreshData();
    } else {
      router.refresh();
    }
  }, [router, onRefreshData]);

  // Get contextual actions based on current route
  const getContextualActions = () => {
    const actions: Array<{
      label: string;
      icon: React.ComponentType<{ className?: string }>;
      onSelect: () => void;
      shortcut?: string;
    }> = [];

    switch (pathname) {
      case "/":
        actions.push({
          label: "Refresh data",
          icon: RiRefreshLine,
          onSelect: handleRefreshData,
        });
        break;
      case "/transactions":
        if (onExportCSV) {
          actions.push({
            label: "Export CSV",
            icon: RiDownloadLine,
            onSelect: onExportCSV,
          });
        }
        actions.push({
          label: "Import CSV",
          icon: RiUploadLine,
          onSelect: () => router.push("/transactions/import"),
        });
        break;
      case "/assets":
        if (onAddAsset) {
          actions.push({
            label: "Add asset",
            icon: RiAddLine,
            onSelect: onAddAsset,
          });
        }
        break;
    }

    return actions;
  };

  const contextualActions = getContextualActions();

  // Determine if we should show search results
  const shouldSearch = search.length >= MIN_SEARCH_LENGTH;

  React.useEffect(() => {
    if (!open || !shouldSearch) {
      setTransactionSearchResults([]);
      setIsSearchingTransactions(false);
      return;
    }

    const normalizedSearch = search.trim();
    if (normalizedSearch.length < MIN_SEARCH_LENGTH) {
      setTransactionSearchResults([]);
      setIsSearchingTransactions(false);
      return;
    }

    const requestId = transactionSearchRequestIdRef.current + 1;
    transactionSearchRequestIdRef.current = requestId;
    setIsSearchingTransactions(true);

    const timeoutId = window.setTimeout(() => {
      searchCommandPaletteTransactions(normalizedSearch)
        .then((results) => {
          if (transactionSearchRequestIdRef.current === requestId) {
            setTransactionSearchResults(results);
          }
        })
        .catch(() => {
          if (transactionSearchRequestIdRef.current === requestId) {
            setTransactionSearchResults([]);
          }
        })
        .finally(() => {
          if (transactionSearchRequestIdRef.current === requestId) {
            setIsSearchingTransactions(false);
          }
        });
    }, 200);

    return () => {
      window.clearTimeout(timeoutId);
    };
  }, [open, search, shouldSearch]);

  // Filter function for search
  const filteredAccounts = React.useMemo(() => {
    if (!data?.accounts || !shouldSearch) return [];
    const term = search.toLowerCase();
    return data.accounts.filter(
      (a) =>
        a.name.toLowerCase().includes(term) ||
        a.institution?.toLowerCase().includes(term)
    );
  }, [data?.accounts, search, shouldSearch]);

  const filteredAssets = React.useMemo(() => {
    if (!data?.assets || !shouldSearch) return [];
    const term = search.toLowerCase();
    return data.assets.filter(
      (a) =>
        a.name.toLowerCase().includes(term) ||
        a.subtitle?.toLowerCase().includes(term)
    );
  }, [data?.assets, search, shouldSearch]);

  const filteredTransactions = React.useMemo(() => {
    if (!shouldSearch) return [];
    return transactionSearchResults;
  }, [shouldSearch, transactionSearchResults]);

  // Check if we have any search results
  const hasSearchResults =
    filteredAccounts.length > 0 ||
    filteredAssets.length > 0 ||
    filteredTransactions.length > 0;

  // Navigation items for filtering
  const navigationItems = [
    { label: "Dashboard", path: "/", icon: RiHomeLine, shortcut: "B" },
    { label: "Transactions", path: "/transactions", icon: RiExchangeLine, shortcut: "T" },
    { label: "Subscriptions", path: "/subscriptions", icon: RiLoopRightLine, shortcut: "S" },
    { label: "Assets", path: "/assets", icon: RiWallet3Line, shortcut: "A" },
    { label: "Settings", path: "/settings", icon: RiSettings3Line, shortcut: "D" },
  ];

  // Theme items for filtering
  const themeItems = [
    { label: "Light Mode", action: () => setTheme("light"), icon: RiSunLine },
    { label: "Dark Mode", action: () => setTheme("dark"), icon: RiMoonLine },
    { label: "Toggle Theme", action: () => setTheme(theme === "dark" ? "light" : "dark"), icon: theme === "dark" ? RiSunLine : RiMoonLine, shortcut: "M" },
  ];

  // Filter navigation items based on search
  const filteredNavigation = React.useMemo(() => {
    if (!search) return navigationItems;
    const term = search.toLowerCase();
    return navigationItems.filter((item) =>
      item.label.toLowerCase().includes(term)
    );
  }, [search]);

  // Filter contextual actions based on search
  const filteredActions = React.useMemo(() => {
    if (!search) return contextualActions;
    const term = search.toLowerCase();
    return contextualActions.filter((action) =>
      action.label.toLowerCase().includes(term)
    );
  }, [search, contextualActions]);

  // Filter theme items based on search
  const filteredTheme = React.useMemo(() => {
    if (!search) return themeItems;
    const term = search.toLowerCase();
    return themeItems.filter((item) =>
      item.label.toLowerCase().includes(term)
    );
  }, [search, themeItems]);

  // Check if we have any filtered command results
  const hasCommandResults =
    filteredNavigation.length > 0 ||
    filteredActions.length > 0 ||
    filteredTheme.length > 0;
  const shouldShowLoading =
    shouldSearch &&
    (isSearchingTransactions ||
      (isLoading && !data && transactionSearchResults.length === 0));

  return (
    <CommandDialog
      open={open}
      onOpenChange={setOpen}
      className="sm:max-w-xl"
    >
      <Command
        className="[&_[cmdk-group-heading]]:text-muted-foreground [&_[cmdk-group-heading]]:font-medium"
        shouldFilter={false}
      >
        <CommandInput
          placeholder="Search or type a command..."
          value={search}
          onValueChange={setSearch}
        />
        <CommandList>
          {shouldShowLoading ? (
            <div className="flex items-center justify-center py-6">
              <RiLoader4Line className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : (
            <>
              {/* Show "no results" when nothing matches */}
              {search && !hasSearchResults && !hasCommandResults && (
                <CommandEmpty>No results found.</CommandEmpty>
              )}

              {/* Search results - only show when searching with 2+ characters */}
              {shouldSearch && hasSearchResults && (
                <>
                  {filteredAccounts.length > 0 && (
                    <CommandGroup heading="ACCOUNTS">
                      {filteredAccounts.map((account) => (
                        <CommandItem
                          key={account.id}
                          onSelect={() => runCommand(() => router.push("/settings"))}
                          className="flex items-center justify-between"
                        >
                          <div className="flex items-center gap-2 min-w-0">
                            <AccountLogo
                              name={account.name}
                              logoUrl={account.logo?.logoUrl}
                              updatedAt={account.logo?.updatedAt}
                              size="sm"
                            />
                            <span className="truncate">{account.name}</span>
                            {account.institution && (
                              <>
                                <span className="text-muted-foreground">·</span>
                                <span className="text-muted-foreground truncate">
                                  {account.institution}
                                </span>
                              </>
                            )}
                          </div>
                          <span className="text-muted-foreground text-sm shrink-0 ml-2">
                            {formatAmount(account.balance, account.currency)}
                          </span>
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  )}

                  {filteredAssets.length > 0 && (
                    <>
                      {filteredAccounts.length > 0 && <CommandSeparator />}
                      <CommandGroup heading="ASSETS">
                        {filteredAssets.map((asset) => (
                          <CommandItem
                            key={asset.id}
                            onSelect={() => runCommand(() => router.push("/assets"))}
                            className="flex items-center justify-between"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <span
                                className="inline-block h-2 w-2 shrink-0 rounded-full"
                                style={{ backgroundColor: asset.categoryColor }}
                              />
                              <span className="truncate">{asset.name}</span>
                              {asset.subtitle && (
                                <>
                                  <span className="text-muted-foreground">·</span>
                                  <span className="text-muted-foreground truncate">
                                    {asset.subtitle}
                                  </span>
                                </>
                              )}
                            </div>
                            <span className="text-muted-foreground text-sm shrink-0 ml-2">
                              {formatAmount(asset.value, asset.currency)}
                            </span>
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </>
                  )}

                  {filteredTransactions.length > 0 && (
                    <>
                      {(filteredAccounts.length > 0 || filteredAssets.length > 0) && (
                        <CommandSeparator />
                      )}
                      <CommandGroup heading="TRANSACTIONS">
                        {filteredTransactions.slice(0, 10).map((tx) => (
                          <CommandItem
                            key={tx.id}
                            onSelect={() =>
                              runCommand(() =>
                                router.push(`/transactions?tx=${tx.id}`)
                              )
                            }
                            className="flex items-center justify-between"
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <RiExchangeLine className="h-4 w-4 shrink-0 text-muted-foreground" />
                              <span className="truncate">
                                {tx.merchant || tx.description || "Transaction"}
                              </span>
                            </div>
                            <div className="flex items-center gap-3 shrink-0 ml-2">
                              <span
                                className={
                                  tx.amount < 0 ? "text-red-500" : "text-green-500"
                                }
                              >
                                {formatAmount(tx.amount, tx.currency)}
                              </span>
                              <span className="text-muted-foreground text-xs">
                                {formatDate(new Date(tx.bookedAt), "short")}
                              </span>
                            </div>
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </>
                  )}
                </>
              )}

              {/* Navigation - filtered based on search */}
              {filteredNavigation.length > 0 && (
                <>
                  {shouldSearch && hasSearchResults && <CommandSeparator />}
                  <CommandGroup heading="NAVIGATION">
                    {filteredNavigation.map((item) => (
                      <CommandItem
                        key={item.path}
                        onSelect={() =>
                          runCommand(() =>
                            router.push(
                              item.path === "/"
                                ? getHomePathWithFilters()
                                : item.path === "/transactions"
                                ? getTransactionsPathWithFilters()
                                : item.path
                            )
                          )
                        }
                      >
                        <item.icon className="mr-2 h-4 w-4" />
                        <span>{item.label}</span>
                        <CommandShortcut>{item.shortcut}</CommandShortcut>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </>
              )}

              {/* Actions - filtered based on search */}
              {filteredActions.length > 0 && (
                <>
                  <CommandSeparator />
                  <CommandGroup heading="ACTIONS">
                    {filteredActions.map((action) => (
                      <CommandItem
                        key={action.label}
                        onSelect={() => runCommand(action.onSelect)}
                      >
                        <action.icon className="mr-2 h-4 w-4" />
                        <span>{action.label}</span>
                        {action.shortcut && (
                          <CommandShortcut>{action.shortcut}</CommandShortcut>
                        )}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </>
              )}

              {/* Theme - filtered based on search */}
              {filteredTheme.length > 0 && (
                <>
                  <CommandSeparator />
                  <CommandGroup heading="THEME">
                    {filteredTheme.map((item) => (
                      <CommandItem
                        key={item.label}
                        onSelect={() => runCommand(item.action)}
                      >
                        <item.icon className="mr-2 h-4 w-4" />
                        <span>{item.label}</span>
                        {item.shortcut && (
                          <CommandShortcut>{item.shortcut}</CommandShortcut>
                        )}
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </>
              )}
            </>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
