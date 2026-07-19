"use client";

import { useQuery } from "@tanstack/react-query";
import { ReportForm } from "@/components/reports/ReportForm";

async function fetchAccounts(): Promise<{ id: string; name: string }[]> {
  const res = await fetch("/api/accounts");
  if (!res.ok) throw new Error("Failed to load accounts");
  return res.json();
}

export default function NewReportPage() {
  const { data: accounts } = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">New report</h1>
      <ReportForm availableAccounts={accounts ?? []} />
    </div>
  );
}
