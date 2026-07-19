import { render } from "@react-email/render";
import { describe, expect, it } from "vitest";
import ReportNewsletter from "../report-newsletter";

describe("ReportNewsletter", () => {
  it("renders balances and transactions", async () => {
    const html = await render(
      ReportNewsletter({
        reportName: "Weekly summary",
        generatedAt: "2026-07-19T08:00:00Z",
        accounts: [{ name: "Checking", institution: "Bank X", balance: "1234.56", currency: "EUR" }],
        transactionsModeLabel: "Last 2 transactions",
        transactions: [
          { description: "Groceries", category: null, date: "2026-07-18", amount: "50.00", currency: "EUR", direction: "out" },
        ],
        manageUrl: "https://app.example.com/reports/1",
      })
    );
    expect(html).toContain("Weekly summary");
    expect(html).toContain("Checking");
    expect(html).toContain("Groceries");
  });

  it("shows an empty state with no transactions", async () => {
    const html = await render(
      ReportNewsletter({
        reportName: "Weekly summary",
        generatedAt: "2026-07-19T08:00:00Z",
        accounts: [],
        transactionsModeLabel: "Last 5 transactions",
        transactions: [],
        manageUrl: "#",
      })
    );
    expect(html).toContain("No transactions to show.");
  });
});
