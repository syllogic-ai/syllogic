"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getReport, listAccounts } from "@/lib/reports/api";
import { ReportForm } from "@/components/reports/ReportForm";

export default function EditReportPage() {
  const params = useParams<{ id: string }>();
  const {
    data: report,
    isLoading: reportLoading,
    isError: reportError,
  } = useQuery({ queryKey: ["reports", params.id], queryFn: () => getReport(params.id) });
  const {
    data: accounts,
    isLoading: accountsLoading,
    isError: accountsError,
  } = useQuery({ queryKey: ["accounts"], queryFn: listAccounts });

  if (reportLoading) return <div className="p-6 text-sm text-muted-foreground">Loading…</div>;

  if (reportError || !report) {
    return (
      <div className="p-6 text-sm text-muted-foreground">
        Report not found or failed to load.{" "}
        <Link href="/reports" className="text-foreground underline underline-offset-4">
          Back to reports
        </Link>
      </div>
    );
  }

  return (
    <div className="p-6 text-foreground">
      <h1 className="text-xl font-semibold mb-4">Edit report</h1>
      <ReportForm
        report={report}
        availableAccounts={accounts ?? []}
        accountsLoading={accountsLoading}
        accountsError={accountsError}
      />
    </div>
  );
}
