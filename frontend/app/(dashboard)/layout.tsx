import { redirect } from "next/navigation";
import { headers } from "next/headers";
import { eq } from "drizzle-orm";
import { auth } from "@/lib/auth";
import { db } from "@/lib/db";
import { users } from "@/lib/db/schema";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/app-sidebar";

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

  // Check onboarding status
  const user = await db.query.users.findFirst({
    where: eq(users.id, session.user.id),
    columns: {
      onboardingStatus: true,
    },
  });

  const onboardingStatus = user?.onboardingStatus ?? "pending";

  // Redirect to appropriate onboarding step if not completed
  if (onboardingStatus !== "completed") {
    switch (onboardingStatus) {
      case "pending":
        redirect("/step-1");
      case "step_1":
        redirect("/step-2");
      case "step_2":
        redirect("/step-3");
      case "step_3":
        redirect("/step-3");
      default:
        redirect("/step-1");
    }
  }

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>{children}</SidebarInset>
    </SidebarProvider>
  );
}
