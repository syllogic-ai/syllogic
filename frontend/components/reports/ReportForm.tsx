"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { z } from "zod";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { createReport, sendTestReport, updateReport } from "@/lib/reports/api";
import type { Report, ReportInput } from "@/lib/reports/types";

const schema = z.object({
  name: z.string().min(1, "Required"),
  account_ids: z.array(z.string()),
  transaction_mode: z.enum(["RECENT", "TOP_N"]),
  transaction_count: z.coerce.number().int().min(1).max(100),
  transaction_direction: z.enum(["ALL", "EXPENSE", "INCOME", "INFLOW", "OUTFLOW"]),
  frequency: z.enum(["DAILY", "WEEKLY", "BIWEEKLY", "MONTHLY"]),
  send_time: z.string().min(1),
  send_day_of_week: z.coerce.number().int().min(0).max(6).nullable().optional(),
  send_day_of_month: z.coerce.number().int().min(1).max(28).nullable().optional(),
  timezone: z.string().min(1),
  recipient_emails: z.array(z.string().email()).min(1, "Add at least one recipient"),
  is_active: z.boolean(),
});

type FormValues = z.infer<typeof schema>;

const DEFAULTS: FormValues = {
  name: "",
  account_ids: [],
  transaction_mode: "RECENT",
  transaction_count: 10,
  transaction_direction: "ALL",
  frequency: "WEEKLY",
  send_time: "08:00:00",
  send_day_of_week: 0,
  send_day_of_month: null,
  timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
  recipient_emails: [],
  is_active: true,
};

export function ReportForm({
  report,
  availableAccounts,
}: {
  report?: Report;
  availableAccounts: { id: string; name: string }[];
}) {
  const router = useRouter();
  const [recipientDraft, setRecipientDraft] = useState("");
  const [sendingTest, setSendingTest] = useState(false);

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: report ? { ...DEFAULTS, ...report } : DEFAULTS,
  });

  const frequency = watch("frequency");
  const recipients = watch("recipient_emails");
  const accountIds = watch("account_ids");

  async function onSubmit(values: FormValues) {
    const input: Partial<ReportInput> = values;
    if (report) {
      await updateReport(report.id, input);
    } else {
      await createReport(input);
    }
    router.push("/reports");
  }

  async function handleSendTest() {
    if (!report) return;
    setSendingTest(true);
    try {
      await sendTestReport(report.id);
    } finally {
      setSendingTest(false);
    }
  }

  function addRecipient() {
    const value = recipientDraft.trim();
    if (!value) return;
    setValue("recipient_emails", [...recipients, value]);
    setRecipientDraft("");
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="max-w-lg space-y-5">
      <div>
        <label className="block text-sm font-medium mb-1">Name</label>
        <input {...register("name")} className="w-full border rounded px-3 py-2 text-sm" />
        {errors.name && <p className="text-xs text-red-600 mt-1">{errors.name.message}</p>}
      </div>

      <div>
        <label className="block text-sm font-medium mb-1">Accounts</label>
        <div className="space-y-1 border rounded p-2 max-h-40 overflow-y-auto">
          {availableAccounts.map((a) => (
            <label key={a.id} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={accountIds.includes(a.id)}
                onChange={(e) =>
                  setValue(
                    "account_ids",
                    e.target.checked ? [...accountIds, a.id] : accountIds.filter((id) => id !== a.id)
                  )
                }
              />
              {a.name}
            </label>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="block text-sm font-medium mb-1">Mode</label>
          <select {...register("transaction_mode")} className="w-full border rounded px-2 py-2 text-sm">
            <option value="RECENT">Most recent</option>
            <option value="TOP_N">Top N by amount</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Count</label>
          <input type="number" {...register("transaction_count")} className="w-full border rounded px-2 py-2 text-sm" />
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Direction</label>
          <select {...register("transaction_direction")} className="w-full border rounded px-2 py-2 text-sm">
            <option value="ALL">All</option>
            <option value="EXPENSE">Expenses</option>
            <option value="INCOME">Income</option>
            <option value="INFLOW">Inflows</option>
            <option value="OUTFLOW">Outflows</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="block text-sm font-medium mb-1">Frequency</label>
          <select {...register("frequency")} className="w-full border rounded px-2 py-2 text-sm">
            <option value="DAILY">Daily</option>
            <option value="WEEKLY">Weekly</option>
            <option value="BIWEEKLY">Biweekly</option>
            <option value="MONTHLY">Monthly</option>
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium mb-1">Time</label>
          <input type="time" step={60} {...register("send_time")} className="w-full border rounded px-2 py-2 text-sm" />
        </div>
      </div>

      {(frequency === "WEEKLY" || frequency === "BIWEEKLY") && (
        <div>
          <label className="block text-sm font-medium mb-1">Day of week</label>
          <select {...register("send_day_of_week")} className="w-full border rounded px-2 py-2 text-sm">
            {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((d, i) => (
              <option key={d} value={i}>
                {d}
              </option>
            ))}
          </select>
        </div>
      )}

      {frequency === "MONTHLY" && (
        <div>
          <label className="block text-sm font-medium mb-1">Day of month</label>
          <input
            type="number"
            min={1}
            max={28}
            {...register("send_day_of_month")}
            className="w-full border rounded px-2 py-2 text-sm"
          />
        </div>
      )}

      <div>
        <label className="block text-sm font-medium mb-1">Recipients</label>
        <div className="flex gap-2 mb-2">
          <input
            value={recipientDraft}
            onChange={(e) => setRecipientDraft(e.target.value)}
            placeholder="name@example.com"
            className="flex-1 border rounded px-3 py-2 text-sm"
          />
          <button type="button" onClick={addRecipient} className="border rounded px-3 py-2 text-sm">
            Add
          </button>
        </div>
        <div className="flex flex-wrap gap-2">
          {recipients.map((email) => (
            <span key={email} className="bg-gray-100 rounded-full px-3 py-1 text-xs flex items-center gap-1">
              {email}
              <button
                type="button"
                onClick={() => setValue("recipient_emails", recipients.filter((r) => r !== email))}
              >
                ×
              </button>
            </span>
          ))}
        </div>
        {errors.recipient_emails && <p className="text-xs text-red-600 mt-1">{errors.recipient_emails.message}</p>}
      </div>

      <div className="flex items-center gap-3 pt-2">
        <button type="submit" disabled={isSubmitting} className="bg-blue-600 text-white rounded px-4 py-2 text-sm">
          {report ? "Save changes" : "Create report"}
        </button>
        {report && (
          <button
            type="button"
            onClick={handleSendTest}
            disabled={sendingTest}
            className="border rounded px-4 py-2 text-sm"
          >
            {sendingTest ? "Sending…" : "Send test now"}
          </button>
        )}
      </div>
    </form>
  );
}
