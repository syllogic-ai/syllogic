import { render } from "@react-email/render";
import { describe, expect, it } from "vitest";
import ReportNewsletter from "../report-newsletter";

const props = {
  reportName: "Syllogic | Weekly Digest",
  generatedAt: "2026-07-20T08:00:00Z",
  periodLabel: "Last 7 days",
  totalBalance: "3394.04",
  totalCurrency: "EUR",
  accounts: [{
    name: "ABN AMRO Giannis", institution: "ABN AMRO",
    logoUrl: "https://app.syllogic.ai/uploads/logos/abnamro.com.png",
    balance: "591.51", currency: "EUR",
  }],
  transactionsModeLabel: "Top 8 expenses",
  transactions: [{ description: "British Airways Plc", date: "2026-07-16", amount: "829.94", currency: "EUR", direction: "out" as const }],
  manageUrl: "https://app.syllogic.ai/reports/1",
};

describe("ReportNewsletter", () => {
  it("renders the period label in the masthead", async () => {
    const html = await render(ReportNewsletter(props));
    expect(html).toContain("Last 7 days");
  });

  it("puts the page backdrop on a table wrapper, not only <body>", async () => {
    // Apple Mail overrides the <body> background but honours table cells,
    // which previously produced a dark card on a light page.
    const html = await render(ReportNewsletter(props));
    expect(html).toContain("sy-page");
  });

  it("ships a prefers-color-scheme dark block", async () => {
    const html = await render(ReportNewsletter(props));
    expect(html).toContain("prefers-color-scheme: dark");
    expect(html).toContain("#121110"); // dark backdrop = --background
  });

  it("uses no rounded corners and no green", async () => {
    const html = await render(ReportNewsletter(props));
    expect(html).not.toContain("border-radius");
    expect(html).not.toContain("#10B981");
  });

  it("omits the total block when the total is unavailable", async () => {
    const html = await render(ReportNewsletter({ ...props, totalBalance: null }));
    expect(html).not.toContain("TOTAL BALANCE");
  });
});
