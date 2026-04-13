import { Suspense } from "react";
import { redirect } from "next/navigation";
import { Header } from "@/components/layout/header";
import { requireAuth } from "@/lib/auth-helpers";
import { BankPicker } from "./bank-picker";
import { RiLoader4Line } from "@remixicon/react";

export default async function ConnectBankPage() {
  const userId = await requireAuth();
  if (!userId) redirect("/login");

  return (
    <>
      <Header title="Connect Bank" />
      <div className="flex flex-1 flex-col p-4 pt-0">
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-12">
              <RiLoader4Line className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          }
        >
          <BankPicker />
        </Suspense>
      </div>
    </>
  );
}
