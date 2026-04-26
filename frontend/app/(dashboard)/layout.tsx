import { redirect } from "next/navigation";
import { cookies } from "next/headers";
import { JetBrains_Mono } from "next/font/google";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { getOnboardingRedirectPath } from "@/lib/actions/onboarding";
import { getCachedSession, getCachedOnboardingStatus } from "@/lib/data/cached";
import { ImportStatusNotifier } from "@/components/import-status-notifier";
import { WalkthroughProvider } from "@/components/walkthrough/walkthrough-provider";

const jbMono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-jb-mono", weight: ["400","500","600","700"] });

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const cookieStore = await cookies();
  const sidebarCookie = cookieStore.get("syllogic.sidebar.open")?.value;
  const defaultSidebarOpen = sidebarCookie === "true";

  const session = await getCachedSession();

  if (!session) {
    redirect("/login");
  }

  // Check onboarding status and redirect if not completed.
  //
  // Note: `redirect()` throws a special Next.js error to trigger navigation.
  // Do NOT wrap this in a broad try/catch, or the redirect will be swallowed.
  const onboardingStatus = await getCachedOnboardingStatus();
  if (onboardingStatus && !onboardingStatus.isCompleted) {
    const redirectPath = await getOnboardingRedirectPath(onboardingStatus.status);
    redirect(redirectPath);
  }

  return (
    <SidebarProvider defaultOpen={defaultSidebarOpen}>
      <WalkthroughProvider>
        <AppSidebar initialUser={session.user} />
        <SidebarInset className={jbMono.variable}>{children}</SidebarInset>
        <ImportStatusNotifier />
      </WalkthroughProvider>
    </SidebarProvider>
  );
}
