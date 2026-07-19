"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getReport } from "@/lib/reports/api";
import { ReportForm } from "@/components/reports/ReportForm";

async function fetchAccounts(): Promise<{ id: string; name: string }[]> {
  const res = await fetch("/api/accounts");
  if (!res.ok) throw new Error("Failed to load accounts");
  return res.json();
}

export default function EditReportPage() {
  const params = useParams<{ id: string }>();
  const { data: report } = useQuery({ queryKey: ["reports", params.id], queryFn: () => getReport(params.id) });
  const { data: accounts } = useQuery({ queryKey: ["accounts"], queryFn: fetchAccounts });

  if (!report) return <div className="p-6 text-sm text-gray-500">Loading…</div>;

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-4">Edit report</h1>
      <ReportForm report={report} availableAccounts={accounts ?? []} />
    </div>
  );
}
