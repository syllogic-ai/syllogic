import type { ReportRunStatus } from "@/lib/reports/types";

const STYLES: Record<ReportRunStatus, string> = {
  SCHEDULED: "bg-gray-100 text-gray-700",
  RUNNING: "bg-blue-100 text-blue-700",
  SUCCEEDED: "bg-green-100 text-green-700",
  FAILED: "bg-red-100 text-red-700",
};

export function RunStatusBadge({ status }: { status: ReportRunStatus }) {
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {status}
    </span>
  );
}
