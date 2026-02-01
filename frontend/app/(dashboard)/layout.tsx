import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { auth } from "@/lib/auth";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/app-sidebar";
import { getOnboardingStatus, getOnboardingRedirectPath } from "@/lib/actions/onboarding";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await auth.api.getSession({
    headers: await headers(),
  });

  if (!session) {
    redirect("/login");
  }

  // Check onboarding status and redirect if not completed
  const onboardingStatus = await getOnboardingStatus();
  if (onboardingStatus && !onboardingStatus.isCompleted) {
    const redirectPath = await getOnboardingRedirectPath(onboardingStatus.status);
    redirect(redirectPath);
  }

  return (
    <SidebarProvider defaultOpen={false}>
      <AppSidebar />
      <SidebarInset>{children}</SidebarInset>
    </SidebarProvider>
  );
}
