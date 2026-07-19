"use client";

import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { getReport, listReportRuns } from "@/lib/reports/api";
import { RunStatusBadge } from "@/components/reports/RunStatusBadge";

export default function ReportRunsPage() {
  const params = useParams<{ id: string }>();
  const { data: report } = useQuery({ queryKey: ["reports", params.id], queryFn: () => getReport(params.id) });
  const {
    data: runs,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["reports", params.id, "runs"],
    queryFn: () => listReportRuns(params.id),
    refetchInterval: 10_000,
  });

  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold mb-1">{report ? `${report.name} — Runs` : "Runs"}</h1>
      <p className="text-sm text-gray-500 mb-4">Scheduled and executed sends for this report.</p>

      {isLoading ? (
        <p className="text-sm text-gray-500">Loading…</p>
      ) : isError ? (
        <p className="text-sm text-red-600">Failed to load runs. Please try again.</p>
      ) : runs && runs.length > 0 ? (
        <table className="w-full text-sm border rounded-lg overflow-hidden">
          <thead className="bg-gray-50 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-4 py-2">Scheduled for</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Finished</th>
              <th className="px-4 py-2">Error</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {runs.map((run) => (
              <tr key={run.id}>
                <td className="px-4 py-2">
                  {run.is_test
                    ? "Test send"
                    : run.scheduled_for
                    ? new Date(run.scheduled_for).toLocaleString()
                    : "—"}
                </td>
                <td className="px-4 py-2">
                  <RunStatusBadge status={run.status} />
                </td>
                <td className="px-4 py-2">{run.finished_at ? new Date(run.finished_at).toLocaleString() : "—"}</td>
                <td className="px-4 py-2 text-red-600">{run.error_message ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <p className="text-sm text-gray-500">No runs yet.</p>
      )}
    </div>
  );
}
