"use client";

import { useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  RiHomeLine,
  RiExchangeLine,
  RiSettings3Line,
  RiLogoutBoxLine,
  RiWallet3Line,
  RiArrowUpDownLine,
  RiLoopRightLine,
  RiArrowRightSLine,
  RiArrowLeftSLine,
} from "@remixicon/react";
import { signOut, useSession } from "@/lib/auth-client";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";

const navItems = [
  {
    title: "Home",
    href: "/",
    icon: RiHomeLine,
  },
  {
    title: "Transactions",
    href: "/transactions",
    icon: RiExchangeLine,
  },
  {
    title: "Subscriptions",
    href: "/subscriptions",
    icon: RiLoopRightLine,
  },
  {
    title: "Assets",
    href: "/assets",
    icon: RiWallet3Line,
  },
  {
    title: "Settings",
    href: "/settings",
    icon: RiSettings3Line,
  },
];

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { data: session } = useSession();
  const { isMobile, state, setOpen } = useSidebar();
  const [hasMarkError, setHasMarkError] = useState(false);
  const isCollapsed = state === "collapsed";
  const brandImageSrc =
    isCollapsed && !hasMarkError
      ? "/brand/syllogic-mark.png"
      : "/brand/syllogic-logo.png";
  const userWithProfilePhoto = session?.user as
    | { profilePhotoPath?: string | null; image?: string | null }
    | undefined;
  const avatarSrc = userWithProfilePhoto?.profilePhotoPath ?? userWithProfilePhoto?.image ?? undefined;

  const handleSignOut = async () => {
    await signOut();
    window.location.href = "/login";
  };

  const getInitials = (name?: string | null) => {
    if (!name) return "U";
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  };

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <div className="flex items-center gap-1">
              <SidebarMenuButton
                size="lg"
                onClick={() => router.push("/")}
                tooltip="Syllogic"
                className={isCollapsed ? "justify-center" : "w-full"}
              >
                <div className="bg-sidebar-accent border-sidebar-border flex aspect-square size-8 items-center justify-center overflow-hidden border shrink-0">
                  <img
                    src={brandImageSrc}
                    alt="Syllogic"
                    className="h-full w-full object-contain"
                    onError={() => {
                      if (isCollapsed) {
                        setHasMarkError(true);
                      }
                    }}
                  />
                </div>
                {!isCollapsed && (
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-medium">Syllogic</span>
                  </div>
                )}
              </SidebarMenuButton>
            </div>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu>
            {navItems.map((item) => {
              const isActive = pathname === item.href;
              return (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    isActive={isActive}
                    tooltip={item.title}
                    onClick={() => router.push(item.href)}
                  >
                    <item.icon className="shrink-0" />
                    {!isCollapsed && <span>{item.title}</span>}
                  </SidebarMenuButton>
                </SidebarMenuItem>
              );
            })}
          </SidebarMenu>
        </SidebarGroup>
        {!isMobile && (
          <SidebarGroup className="mt-auto pt-2">
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  onClick={() => setOpen((prev) => !prev)}
                  tooltip={isCollapsed ? "Expand sidebar" : "Collapse sidebar"}
                >
                  {isCollapsed ? (
                    <RiArrowRightSLine className="shrink-0" />
                  ) : (
                    <RiArrowLeftSLine className="shrink-0" />
                  )}
                  {!isCollapsed && <span>Collapse</span>}
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroup>
        )}
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <SidebarMenuButton
                  size="lg"
                  className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
                >
                  <Avatar className="h-8 w-8 shrink-0">
                    <AvatarImage
                      src={avatarSrc}
                      alt={session?.user?.name || "User"}
                    />
                    <AvatarFallback>
                      {getInitials(session?.user?.name)}
                    </AvatarFallback>
                  </Avatar>
                  {!isCollapsed && (
                    <>
                      <div className="grid flex-1 text-left text-sm leading-tight">
                        <span className="truncate font-medium">
                          {session?.user?.name || "User"}
                        </span>
                        <span className="truncate text-xs">
                          {session?.user?.email}
                        </span>
                      </div>
                      <RiArrowUpDownLine className="ml-auto size-4" />
                    </>
                  )}
                </SidebarMenuButton>
              </DropdownMenuTrigger>
              <DropdownMenuContent
                className="min-w-56"
                side={isMobile ? "bottom" : "right"}
                align="end"
                sideOffset={4}
              >
                <DropdownMenuItem onClick={() => router.push("/settings")}>
                  <RiSettings3Line className="mr-2" />
                  Settings
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleSignOut}>
                  <RiLogoutBoxLine className="mr-2" />
                  Log out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
