"use client";

import { useQuery } from "@tanstack/react-query";
import { listAccounts } from "@/lib/reports/api";
import { ReportForm } from "@/components/reports/ReportForm";

export default function NewReportPage() {
  const {
    data: accounts,
    isLoading: accountsLoading,
    isError: accountsError,
  } = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">New report</h1>
      <ReportForm
        availableAccounts={accounts ?? []}
        accountsLoading={accountsLoading}
        accountsError={accountsError}
      />
    </div>
  );
}
