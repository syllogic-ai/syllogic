"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteReport, listReports } from "@/lib/reports/api";

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
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Reports</h1>
        <Link href="/reports/new" className="text-sm font-medium text-blue-600">
          New report
        </Link>
      </div>

      {deleteError && <p className="text-sm text-red-600 mb-4">{deleteError}</p>}

      {isLoading ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : isError ? (
        <div className="text-sm text-gray-500">
          Failed to load reports.{" "}
          <button onClick={() => refetch()} className="text-blue-600 font-medium">
            Retry
          </button>
        </div>
      ) : reports && reports.length > 0 ? (
        <ul className="divide-y divide-gray-200 border rounded-lg">
          {reports.map((report) => (
            <li key={report.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <Link href={`/reports/${report.id}`} className="font-medium text-gray-900">
                  {report.name}
                </Link>
                <p className="text-xs text-gray-500">
                  {report.frequency.toLowerCase()} · next run{" "}
                  {report.next_run_at ? new Date(report.next_run_at).toLocaleString() : "—"} ·{" "}
                  {report.is_active ? "active" : "paused"}
                </p>
              </div>
              <div className="flex gap-3">
                <Link href={`/reports/${report.id}/runs`} className="text-sm text-gray-600">
                  Runs
                </Link>
                <button onClick={() => handleDelete(report.id)} className="text-sm text-red-600">
                  Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-gray-500">No reports yet. Create one to get started.</p>
      )}
    </div>
  );
}
