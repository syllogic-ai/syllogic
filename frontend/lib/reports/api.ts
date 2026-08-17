import type { Report, ReportInput, ReportRun } from "./types";
import type { PickerAccount } from "./account-groups";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Request to ${path} failed (${res.status}): ${body}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export function listReports(): Promise<Report[]> {
  return request<Report[]>("/reports");
}

export function getReport(id: string): Promise<Report> {
  return request<Report>(`/reports/${id}`);
}

export function createReport(input: Partial<ReportInput>): Promise<Report> {
  return request<Report>("/reports", { method: "POST", body: JSON.stringify(input) });
}

export function updateReport(id: string, input: Partial<ReportInput>): Promise<Report> {
  return request<Report>(`/reports/${id}`, { method: "PATCH", body: JSON.stringify(input) });
}

export function deleteReport(id: string): Promise<void> {
  return request<void>(`/reports/${id}`, { method: "DELETE" });
}

export function sendTestReport(id: string): Promise<ReportRun> {
  return request<ReportRun>(`/reports/${id}/send-test`, { method: "POST" });
}

export function listReportRuns(id: string): Promise<ReportRun[]> {
  return request<ReportRun[]>(`/reports/${id}/runs`);
}

// Fetch all accounts, including inactive ones. AccountPicker is responsible
// for hiding inactive accounts by default while still surfacing any that are
// already selected on a report (see is_active handling there) — filtering
// them out here would silently hide a report's configured-but-deactivated
// accounts with no way to see or untick them.
export function listAccounts(): Promise<PickerAccount[]> {
  return request<PickerAccount[]>("/accounts?include_inactive=true");
}

/**
 * People and ownership live in Next.js/Drizzle routes, not the FastAPI
 * backend, so these bypass the /api/[...path] proxy used by `request`.
 */
export async function listPeople(): Promise<{ id: string; name: string }[]> {
  const res = await fetch("/api/people");
  if (!res.ok) throw new Error(`Failed to load people (${res.status})`);
  const body = await res.json();
  return body.people ?? [];
}

export async function listOwners(
  accountIds: string[]
): Promise<Record<string, { personId: string }[]>> {
  if (accountIds.length === 0) return {};
  const res = await fetch("/api/owners/batch", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account: accountIds }),
  });
  if (!res.ok) throw new Error(`Failed to load owners (${res.status})`);
  const body = await res.json();
  return body.account ?? {};
}
