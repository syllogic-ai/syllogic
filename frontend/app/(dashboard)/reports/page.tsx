"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteReport, listReports } from "@/lib/reports/api";
import { buttonVariants } from "@/components/ui/button";

export default function ReportsPage() {
  const queryClient = useQueryClient();
  const {
    data: reports,
    isLoading,
    isError,
    refetch,
  } = useQuery({ queryKey: ["reports"], queryFn: listReports });
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleDelete(id: string) {
    if (!window.confirm("Delete this report? This cannot be undone.")) return;
    setDeleteError(null);
    try {
      await deleteReport(id);
      queryClient.invalidateQueries({ queryKey: ["reports"] });
    } catch (err) {
      setDeleteError(err instanceof Error ? err.message : "Failed to delete report. Please try again.");
    }
  }

  return (
    <div className="p-6 text-foreground">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Reports</h1>
        <Link href="/reports/new" className={buttonVariants({ size: "sm" })}>
          New report
        </Link>
      </div>

      {deleteError && <p className="text-sm text-destructive mb-4">{deleteError}</p>}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : isError ? (
        <div className="text-sm text-muted-foreground">
          Failed to load reports.{" "}
          <button onClick={() => refetch()} className="text-foreground font-medium underline underline-offset-4">
            Retry
          </button>
        </div>
      ) : reports && reports.length > 0 ? (
        <ul className="divide-y divide-border border border-border rounded-lg">
          {reports.map((report) => (
            <li key={report.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <Link href={`/reports/${report.id}`} className="font-medium text-foreground hover:underline">
                  {report.name}
                </Link>
                <p className="text-xs text-muted-foreground">
                  {report.frequency.toLowerCase()} · next run{" "}
                  {report.next_run_at ? new Date(report.next_run_at).toLocaleString() : "—"} ·{" "}
                  {report.is_active ? "active" : "paused"}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <Link href={`/reports/${report.id}/runs`} className="text-sm text-muted-foreground hover:text-foreground">
                  Runs
                </Link>
                <button onClick={() => handleDelete(report.id)} className="text-sm text-destructive hover:underline">
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">No reports yet. Create one to get started.</p>
      )}
    </div>
  );
}
