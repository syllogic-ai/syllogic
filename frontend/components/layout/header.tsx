"use client";

import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";

interface HeaderProps {
  title?: string;
  action?: React.ReactNode;
  shortcut?: string;
}

export function Header({ title, action, shortcut }: HeaderProps) {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-2 transition-[width,height] ease-linear group-has-[[data-collapsible=icon]]/sidebar-wrapper:h-12">
      <div className="flex items-center gap-2 px-4">
        <SidebarTrigger className="-ml-1" />
        <Separator orientation="vertical" className="mr-2 h-4" />
        {title && (
          <div className="flex items-center gap-2">
            <h1 className="text-sm font-medium">{title}</h1>
            {shortcut && (
              <kbd className="pointer-events-none hidden h-5 select-none items-center border bg-muted px-1.5 font-mono text-[10px] font-medium opacity-60 sm:flex">
                {shortcut}
              </kbd>
            )}
          </div>
        )}
      </div>
      {action && <div className="px-4">{action}</div>}
    </header>
  );
}
