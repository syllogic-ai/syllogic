import type { Report, ReportInput, ReportRun } from "./types";

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

export function listAccounts(): Promise<{ id: string; name: string }[]> {
  // Backend route is registered at GET /api/accounts/ (trailing slash).
  // Without it, FastAPI issues a 307 redirect that the internal-auth-signed
  // proxy request doesn't survive correctly.
  return request<{ id: string; name: string }[]>("/accounts/");
}
