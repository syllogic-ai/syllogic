import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { HoldingsTableHF } from "./HoldingsTableHF";
import type { Holding } from "@/lib/api/investments";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mockPush, refresh: vi.fn() }) }));
vi.mock("@/lib/api/investments", () => ({
  updateHolding: vi.fn(),
}));

const H: Holding[] = [
  {
    id: "1",
    account_id: "a",
    symbol: "VUAA",
    name: "Vanguard",
    currency: "USD",
    instrument_type: "etf",
    quantity: "10",
    source: "manual",
    current_price: "100",
    current_value_user_currency: "1000",
    is_stale: false,
  },
  {
    id: "2",
    account_id: "a",
    symbol: "MSFT",
    name: "Microsoft",
    currency: "USD",
    instrument_type: "equity",
    quantity: "5",
    source: "manual",
    current_price: "400",
    current_value_user_currency: "2000",
    is_stale: true,
  },
];

const BROKER_HOLDING: Holding = {
  id: "3",
  account_id: "a",
  symbol: "AAPL",
  name: "Apple",
  currency: "USD",
  instrument_type: "equity",
  quantity: "2",
  source: "ibkr_flex",
  current_price: "200",
  current_value_user_currency: "400",
  is_stale: false,
};

describe("HoldingsTableHF", () => {
  it("filters to ETF only when filter clicked", () => {
    render(
      <HoldingsTableHF
        holdings={H}
        accountNames={{ a: "Acct" }}
        accountsCount={1}
        portfolioCurrencySymbol="€"
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Filter ETF" }));
    expect(screen.queryByText("MSFT")).toBeNull();
    expect(screen.getByText("VUAA")).toBeTruthy();
  });
  it("flags stale rows with amber background", () => {
    render(
      <HoldingsTableHF
        holdings={H}
        accountNames={{ a: "Acct" }}
        accountsCount={1}
        portfolioCurrencySymbol="€"
      />,
    );
    // Find the row containing MSFT (the stale holding) and check class
    const msftCell = screen.getByText("MSFT");
    const row = msftCell.closest("tr");
    expect(row?.className).toMatch(/bg-amber/);
  });
});

describe("HoldingsTableHF row navigation", () => {
  beforeEach(() => mockPush.mockClear());

  it("navigates to holding detail on row click", () => {
    render(
      <HoldingsTableHF
        holdings={H}
        accountNames={{ a: "Acct" }}
        accountsCount={1}
        portfolioCurrencySymbol="€"
      />,
    );
    fireEvent.click(screen.getByText("VUAA"));
    expect(mockPush).toHaveBeenCalledWith("/investments/1");
  });

  it("opens row actions menu without navigating when ellipsis clicked", async () => {
    render(
      <HoldingsTableHF
        holdings={H}
        accountNames={{ a: "Acct" }}
        accountsCount={1}
        portfolioCurrencySymbol="€"
      />,
    );
    const triggers = screen.getAllByRole("button", { name: "Row actions" });
    fireEvent.click(triggers[0]);
    expect(mockPush).not.toHaveBeenCalled();
    // Menu should render Edit/Delete for manual rows
    expect(await screen.findByText("Edit")).toBeTruthy();
  });

  it("calls onDelete with id when Delete menu item then confirm clicked", async () => {
    const onDelete = vi.fn();
    render(
      <HoldingsTableHF
        holdings={H}
        accountNames={{ a: "Acct" }}
        accountsCount={1}
        portfolioCurrencySymbol="€"
        onDelete={onDelete}
      />,
    );
    // MSFT (id "2") sorts first by value (2000 > 1000)
    const triggers = screen.getAllByRole("button", { name: "Row actions" });
    fireEvent.click(triggers[0]);
    const deleteItem = await screen.findByText("Delete");
    fireEvent.click(deleteItem);
    // AlertDialog "Delete" button confirms
    const confirmBtn = await screen.findByRole("button", { name: "Delete" });
    fireEvent.click(confirmBtn);
    expect(onDelete).toHaveBeenCalledWith("2");
    expect(mockPush).not.toHaveBeenCalled();
  });

  it("shows only View details (no Edit/Delete) for non-manual rows", async () => {
    render(
      <HoldingsTableHF
        holdings={[BROKER_HOLDING]}
        accountNames={{ a: "Acct" }}
        accountsCount={1}
        portfolioCurrencySymbol="€"
      />,
    );
    const trigger = screen.getByRole("button", { name: "Row actions" });
    fireEvent.click(trigger);
    expect(await screen.findByText("View details")).toBeTruthy();
    expect(screen.queryByText("Edit")).toBeNull();
    expect(screen.queryByText("Delete")).toBeNull();
  });
});
