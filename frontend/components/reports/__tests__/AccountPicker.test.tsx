import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AccountPicker } from "../AccountPicker";

vi.mock("@/lib/reports/api", () => ({
  listPeople: vi.fn(),
  listOwners: vi.fn(),
}));
import { listOwners, listPeople } from "@/lib/reports/api";

const accounts = [
  { id: "a1", name: "Revo Giannis", account_type: "checking", institution: "Revolut", is_active: true },
  { id: "a2", name: "IBKR", account_type: "investment_brokerage", institution: "Interactive Brokers", is_active: true },
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

  it("hides an inactive account that is not selected", async () => {
    const withInactive = [
      ...accounts,
      { id: "a3", name: "Dead ABN AMRO", account_type: "checking", institution: "ABN AMRO", is_active: false },
    ];
    render(<AccountPicker accounts={withInactive} selectedIds={[]} onChange={() => {}} loading={false} error={false} />);
    await waitFor(() => expect(screen.getByText(/Revo Giannis/)).toBeTruthy());
    expect(screen.queryByText(/Dead ABN AMRO/)).toBeNull();
  });

  it("shows an inactive but selected account, marked inactive", async () => {
    const withInactive = [
      ...accounts,
      { id: "a3", name: "Dead ABN AMRO", account_type: "checking", institution: "ABN AMRO", is_active: false },
    ];
    render(
      <AccountPicker accounts={withInactive} selectedIds={["a3"]} onChange={() => {}} loading={false} error={false} />
    );
    await waitFor(() => expect(screen.getByText(/Dead ABN AMRO/)).toBeTruthy());
    expect(screen.getByText(/inactive/i)).toBeTruthy();
    const checkbox = screen.getByRole("checkbox", { name: /Dead ABN AMRO/i });
    expect((checkbox as HTMLInputElement).checked).toBe(true);
  });

  it("lets an inactive selected account be deselected", async () => {
    const withInactive = [
      ...accounts,
      { id: "a3", name: "Dead ABN AMRO", account_type: "checking", institution: "ABN AMRO", is_active: false },
    ];
    const onChange = vi.fn();
    render(
      <AccountPicker accounts={withInactive} selectedIds={["a3"]} onChange={onChange} loading={false} error={false} />
    );
    const checkbox = await screen.findByRole("checkbox", { name: /Dead ABN AMRO/i });
    fireEvent.click(checkbox);
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
