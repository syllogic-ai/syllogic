export type TransactionMode = "RECENT" | "TOP_N";
export type TransactionDirection = "ALL" | "EXPENSE" | "INCOME" | "INFLOW" | "OUTFLOW";
export type ReportFrequency = "DAILY" | "WEEKLY" | "BIWEEKLY" | "MONTHLY";
export type ReportRunStatus = "SCHEDULED" | "RUNNING" | "SUCCEEDED" | "FAILED";

export type Report = {
  id: string;
  name: string;
  account_ids: string[];
  transaction_mode: TransactionMode;
  transaction_count: number;
  transaction_direction: TransactionDirection;
  frequency: ReportFrequency;
  send_time: string;
  send_day_of_week: number | null;
  send_day_of_month: number | null;
  timezone: string;
  recipient_emails: string[];
  is_active: boolean;
  next_run_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ReportRun = {
  id: string;
  scheduled_for: string | null;
  is_test: boolean;
  started_at: string | null;
  finished_at: string | null;
  status: ReportRunStatus;
  error_message: string | null;
  recipient_emails: string[];
  created_at: string;
};

export type ReportInput = Omit<Report, "id" | "next_run_at" | "created_at" | "updated_at">;
