"use client";

import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteReport, listReports } from "@/lib/reports/api";

export default function ReportsPage() {
  const queryClient = useQueryClient();
  const { data: reports, isLoading } = useQuery({ queryKey: ["reports"], queryFn: listReports });

  async function handleDelete(id: string) {
    await deleteReport(id);
    queryClient.invalidateQueries({ queryKey: ["reports"] });
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Reports</h1>
        <Link href="/reports/new" className="text-sm font-medium text-blue-600">
          New report
        </Link>
      </div>

      {isLoading ? (
        <p className="text-sm text-gray-500">Loading…</p>
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
