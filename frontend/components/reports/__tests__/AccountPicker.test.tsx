import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AccountPicker } from "../AccountPicker";

vi.mock("@/lib/reports/api", () => ({
  listPeople: vi.fn(),
  listOwners: vi.fn(),
}));
import { listOwners, listPeople } from "@/lib/reports/api";

const accounts = [
  { id: "a1", name: "Revo Giannis", account_type: "checking", institution: "Revolut" },
  { id: "a2", name: "IBKR", account_type: "investment_brokerage", institution: "Interactive Brokers" },
];

beforeEach(() => {
  vi.mocked(listPeople).mockResolvedValue([{ id: "p1", name: "Giannis" }]);
  vi.mocked(listOwners).mockResolvedValue({ a1: [{ personId: "p1" }] });
});

describe("AccountPicker", () => {
  it("renders group headings", async () => {
    render(<AccountPicker accounts={accounts} selectedIds={[]} onChange={() => {}} loading={false} error={false} />);
    await waitFor(() => expect(screen.getByText(/Revo Giannis/)).toBeTruthy());
    expect(screen.getByText("Cash")).toBeTruthy();
    expect(screen.getByText("Investment")).toBeTruthy();
  });

  it("shows the owning person", async () => {
    render(<AccountPicker accounts={accounts} selectedIds={[]} onChange={() => {}} loading={false} error={false} />);
    await waitFor(() => expect(screen.getByText("Giannis")).toBeTruthy());
  });

  it("still renders accounts when the owners request fails", async () => {
    // Ownership is decoration; failing to load it must not break selection.
    vi.mocked(listOwners).mockRejectedValue(new Error("boom"));
    render(<AccountPicker accounts={accounts} selectedIds={[]} onChange={() => {}} loading={false} error={false} />);
    await waitFor(() => expect(screen.getByText(/Revo Giannis/)).toBeTruthy());
  });
});
