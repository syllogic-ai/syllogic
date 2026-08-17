import { describe, expect, it } from "vitest";
import { groupAccounts } from "../account-groups";

const acct = (id: string, name: string, account_type: string) => ({
  id,
  name,
  account_type,
  institution: null,
  is_active: true,
});

describe("groupAccounts", () => {
  it("groups by asset category in canonical order", () => {
    const groups = groupAccounts([
      acct("1", "IBKR", "investment_brokerage"),
      acct("2", "Checking", "checking"),
      acct("3", "Savings", "savings"),
    ]);
    expect(groups.map((g) => g.key)).toEqual(["cash", "savings", "investment"]);
    expect(groups[0].accounts.map((a) => a.name)).toEqual(["Checking"]);
  });

  it("maps every investment variant into one group", () => {
    const groups = groupAccounts([
      acct("1", "A", "investment"),
      acct("2", "B", "investment_brokerage"),
      acct("3", "C", "investment_manual"),
    ]);
    expect(groups).toHaveLength(1);
    expect(groups[0].key).toBe("investment");
    expect(groups[0].accounts).toHaveLength(3);
  });

  it("omits empty groups", () => {
    const groups = groupAccounts([acct("1", "Checking", "checking")]);
    expect(groups).toHaveLength(1);
  });

  it("routes unknown types to other", () => {
    const groups = groupAccounts([acct("1", "Mystery", "wat")]);
    expect(groups[0].key).toBe("other");
  });

  it("returns an empty array for no accounts", () => {
    expect(groupAccounts([])).toEqual([]);
  });
});
