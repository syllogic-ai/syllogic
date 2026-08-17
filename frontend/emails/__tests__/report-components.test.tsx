import { render } from "@react-email/render";
import { describe, expect, it } from "vitest";
import { BalancesSection } from "../components/report/BalancesSection";
import { TotalBalance } from "../components/report/TotalBalance";
import { TransactionsSection } from "../components/report/TransactionsSection";

describe("BalancesSection", () => {
  it("renders a logo image when one is present", async () => {
    const html = await render(
      BalancesSection({
        accounts: [{
          name: "ABN AMRO Giannis", institution: "ABN AMRO",
          logoUrl: "https://app.syllogic.ai/uploads/logos/abnamro.com.png",
          balance: "591.51", currency: "EUR",
        }],
      })
    );
    expect(html).toContain("https://app.syllogic.ai/uploads/logos/abnamro.com.png");
    expect(html).toContain("ABN AMRO Giannis");
  });

  it("falls back to a lettered tile when there is no logo", async () => {
    const html = await render(
      BalancesSection({
        accounts: [{ name: "My Brokerage", institution: null, logoUrl: null, balance: "0.00", currency: "EUR" }],
      })
    );
    expect(html).not.toContain("<img");
    expect(html).toContain("M");
  });
});

describe("TotalBalance", () => {
  it("renders the amount when available", async () => {
    const html = await render(TotalBalance({ amount: "3394.04", currency: "EUR" }));
    expect(html).toMatch(/total balance/i);
  });

  it("renders nothing when the total is unavailable", async () => {
    const html = await render(TotalBalance({ amount: null, currency: "EUR" }));
    expect(html).not.toMatch(/total balance/i);
  });
});

describe("TransactionsSection", () => {
  it("uses destructive red for outflows and never green", async () => {
    const html = await render(
      TransactionsSection({
        modeLabel: "Top 8 expenses",
        items: [{ description: "British Airways Plc", date: "2026-07-16", amount: "829.94", currency: "EUR", direction: "out" }],
      })
    );
    expect(html).toContain("#DC2626");
    expect(html).not.toContain("#10B981");
  });

  it("shows an empty state scoped to the period", async () => {
    const html = await render(TransactionsSection({ modeLabel: "Top 10 expenses", items: [] }));
    expect(html).toContain("No transactions in this period.");
  });
});
