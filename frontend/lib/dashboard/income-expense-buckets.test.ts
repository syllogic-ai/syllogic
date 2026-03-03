import { describe, expect, it } from "vitest";
import {
  buildIncomeExpenseBuckets,
  resolveIncomeExpenseGrouping,
} from "@/lib/dashboard/income-expense-buckets";

function localDate(year: number, month: number, day: number): Date {
  return new Date(year, month - 1, day, 12, 0, 0, 0);
}

describe("income-expense-buckets", () => {
  it("uses daily grouping and returns one bucket per day for 7-day ranges", () => {
    const startDate = localDate(2026, 2, 25);
    const endDate = localDate(2026, 3, 3);
    expect(resolveIncomeExpenseGrouping(startDate, endDate)).toBe("day");

    const buckets = buildIncomeExpenseBuckets({
      startDate,
      endDate,
      dailyData: [
        { date: "2026-02-25", income: 100, expenses: 40 },
        { date: "2026-02-27", income: 30, expenses: 20 },
        { date: "2026-03-03", income: 15, expenses: 10 },
      ],
    });

    expect(buckets.length).toBe(7);
    expect(buckets[0]).toEqual({
      month: "Feb 25",
      monthDate: "2026-02-25",
      income: 100,
      expenses: 40,
      tooltipLabel: "Feb 25, 2026",
    });
    expect(buckets[1]).toEqual({
      month: "Feb 26",
      monthDate: "2026-02-26",
      income: 0,
      expenses: 0,
      tooltipLabel: "Feb 26, 2026",
    });
    expect(buckets[6]).toEqual({
      month: "Mar 3",
      monthDate: "2026-03-03",
      income: 15,
      expenses: 10,
      tooltipLabel: "Mar 3, 2026",
    });
  });

  it("uses weekly grouping and returns 4-5 buckets for 30-day ranges", () => {
    const startDate = localDate(2026, 1, 1);
    const endDate = localDate(2026, 1, 30);
    expect(resolveIncomeExpenseGrouping(startDate, endDate)).toBe("week");

    const dailyData = Array.from({ length: 30 }, (_, index) => ({
      date: `2026-01-${String(index + 1).padStart(2, "0")}`,
      income: 10,
      expenses: 6,
    }));

    const buckets = buildIncomeExpenseBuckets({
      startDate,
      endDate,
      dailyData,
    });

    expect(buckets.length).toBe(5);
    expect(buckets.map((bucket) => bucket.monthDate)).toEqual([
      "2026-01-01",
      "2026-01-08",
      "2026-01-15",
      "2026-01-22",
      "2026-01-29",
    ]);
    expect(buckets.map((bucket) => bucket.income)).toEqual([70, 70, 70, 70, 20]);
    expect(buckets.map((bucket) => bucket.expenses)).toEqual([42, 42, 42, 42, 12]);
    expect(buckets[0].tooltipLabel).toBe("Jan 1, 2026 - Jan 7, 2026");
    expect(buckets[4].tooltipLabel).toBe("Jan 29, 2026 - Jan 30, 2026");
  });

  it("uses monthly grouping and preserves 12-month behavior", () => {
    const startDate = localDate(2025, 3, 1);
    const endDate = localDate(2026, 2, 28);
    expect(resolveIncomeExpenseGrouping(startDate, endDate)).toBe("month");

    const monthlyPoints = [
      { date: "2025-03-15", income: 100, expenses: 40 },
      { date: "2025-07-05", income: 200, expenses: 120 },
      { date: "2025-12-20", income: 50, expenses: 60 },
      { date: "2026-02-10", income: 300, expenses: 150 },
    ];

    const buckets = buildIncomeExpenseBuckets({
      startDate,
      endDate,
      dailyData: monthlyPoints,
    });

    expect(buckets.length).toBe(12);
    expect(buckets[0]).toEqual({
      month: "Mar 25",
      monthDate: "2025-03-01",
      income: 100,
      expenses: 40,
      tooltipLabel: "March 2025",
    });
    expect(buckets[4]).toEqual({
      month: "Jul 25",
      monthDate: "2025-07-01",
      income: 200,
      expenses: 120,
      tooltipLabel: "July 2025",
    });
    expect(buckets[9]).toEqual({
      month: "Dec 25",
      monthDate: "2025-12-01",
      income: 50,
      expenses: 60,
      tooltipLabel: "December 2025",
    });
    expect(buckets[11]).toEqual({
      month: "Feb 26",
      monthDate: "2026-02-01",
      income: 300,
      expenses: 150,
      tooltipLabel: "February 2026",
    });
  });
});
