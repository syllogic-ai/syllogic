import path from "node:path";
import { spawnSync } from "node:child_process";
import { describe, expect, it } from "vitest";

const scriptPath = path.resolve(__dirname, "../render-report.ts");
const cwd = path.resolve(__dirname, "../..");

function runRenderReport(input: string) {
  return spawnSync("npx", ["tsx", scriptPath], {
    input,
    cwd,
    encoding: "utf-8",
  });
}

describe("render-report.ts subprocess failure path", () => {
  it("exits non-zero with stderr output on malformed JSON stdin", () => {
    const result = runRenderReport("{ this is not valid json");

    expect(result.status).not.toBe(0);
    expect(result.stderr).toBeTruthy();
    expect(result.stderr.length).toBeGreaterThan(0);
    expect(result.stdout).toBe("");
  }, 30000);

  it("exits non-zero with stderr output when required 'transactions' field is missing", () => {
    const input = JSON.stringify({
      report_name: "Weekly summary",
      generated_at: "2026-07-19T08:00:00Z",
      accounts: [],
      manage_url: "https://app.example.com/reports/1",
      // transactions field intentionally omitted
    });

    const result = runRenderReport(input);

    expect(result.status).not.toBe(0);
    expect(result.stderr).toBeTruthy();
    expect(result.stderr.length).toBeGreaterThan(0);
    expect(result.stdout).toBe("");
  }, 30000);

  it("succeeds with exit code 0 and valid JSON output on well-formed input", () => {
    const input = JSON.stringify({
      report_name: "Weekly summary",
      generated_at: "2026-07-19T08:00:00Z",
      accounts: [{ name: "Checking", institution: "Bank X", balance: "1234.56", currency: "EUR" }],
      transactions: {
        mode_label: "Last 2 transactions",
        items: [
          { description: "Groceries", category: null, date: "2026-07-18", amount: "50.00", currency: "EUR", direction: "out" },
        ],
      },
      manage_url: "https://app.example.com/reports/1",
    });

    const result = runRenderReport(input);

    expect(result.status).toBe(0);
    const parsed = JSON.parse(result.stdout);
    expect(parsed.html).toContain("Weekly summary");
    expect(parsed.text).toBeTruthy();
  }, 30000);

  it("maps payload logo_url onto the camelCase logoUrl prop", () => {
    // Regression guard: a mismatch here fails silently — every account would
    // fall back to the lettered tile and no logo would ever render.
    const input = JSON.stringify({
      report_name: "R",
      generated_at: "2026-07-20T08:00:00Z",
      period_label: "Last 7 days",
      total_balance: "100.00",
      total_currency: "EUR",
      accounts: [{
        name: "ABN",
        institution: "ABN AMRO",
        balance: "50.00",
        currency: "EUR",
        logo_url: "https://app.syllogic.ai/uploads/logos/abnamro.com.png",
      }],
      transactions: { mode_label: "Top 5 expenses", items: [] },
      manage_url: "https://app.syllogic.ai/reports/1",
    });

    const result = runRenderReport(input);

    expect(result.status).toBe(0);
    const { html } = JSON.parse(result.stdout);
    expect(html).toContain("https://app.syllogic.ai/uploads/logos/abnamro.com.png");
  }, 30000);
});
