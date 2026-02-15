import { describe, expect, it } from "vitest";
import { buildConservativeSankey } from "@/lib/dashboard/sankey";

function sumOutgoingBySource(
  links: { source: number; target: number; value: number }[],
  source: number
): number {
  return links
    .filter((link) => link.source === source)
    .reduce((sum, link) => sum + link.value, 0);
}

function sumIncomingByTarget(
  links: { source: number; target: number; value: number }[],
  target: number
): number {
  return links
    .filter((link) => link.target === target)
    .reduce((sum, link) => sum + link.value, 0);
}

describe("buildConservativeSankey", () => {
  it("preserves totals for balanced income and expense categories", () => {
    const result = buildConservativeSankey(
      [
        { categoryId: "i1", categoryName: "Salary", total: 3000, categoryType: "income" },
        { categoryId: "i2", categoryName: "Freelance", total: 500, categoryType: "income" },
      ],
      [
        { categoryId: "e1", categoryName: "Rent", total: 1500, categoryType: "expense" },
        { categoryId: "e2", categoryName: "Food", total: 1000, categoryType: "expense" },
        { categoryId: "e3", categoryName: "Other", total: 1000, categoryType: "expense" },
      ]
    );

    const incomeNodes = result.nodes
      .map((node, index) => ({ node, index }))
      .filter(({ node }) => node.categoryType === "income");
    const expenseNodes = result.nodes
      .map((node, index) => ({ node, index }))
      .filter(({ node }) => node.categoryType === "expense");

    for (const { node, index } of incomeNodes) {
      expect(sumOutgoingBySource(result.links, index)).toBeCloseTo(node.total ?? 0, 6);
    }

    for (const { node, index } of expenseNodes) {
      expect(sumIncomingByTarget(result.links, index)).toBeCloseTo(node.total ?? 0, 6);
    }
  });

  it("adds synthetic Savings expense node when income exceeds expenses", () => {
    const result = buildConservativeSankey(
      [{ categoryId: "i1", categoryName: "Salary", total: 4000, categoryType: "income" }],
      [{ categoryId: "e1", categoryName: "Rent", total: 2500, categoryType: "expense" }]
    );

    const savingsNode = result.nodes.find((node) => node.name === "Savings");
    expect(savingsNode).toBeDefined();
    expect(savingsNode?.categoryId).toBeUndefined();
    expect(savingsNode?.categoryType).toBe("expense");

    result.links.forEach((link) => {
      expect(Number.isFinite(link.value)).toBe(true);
      expect(link.value).toBeGreaterThan(0);
    });
  });

  it("adds synthetic Funding Gap income node when expenses exceed income", () => {
    const result = buildConservativeSankey(
      [{ categoryId: "i1", categoryName: "Salary", total: 1000, categoryType: "income" }],
      [{ categoryId: "e1", categoryName: "Rent", total: 1900, categoryType: "expense" }]
    );

    const fundingGapNode = result.nodes.find((node) => node.name === "Funding Gap");
    expect(fundingGapNode).toBeDefined();
    expect(fundingGapNode?.categoryId).toBeUndefined();
    expect(fundingGapNode?.categoryType).toBe("income");

    const incomeNodes = result.nodes
      .map((node, index) => ({ node, index }))
      .filter(({ node }) => node.categoryType === "income");
    const expenseNodes = result.nodes
      .map((node, index) => ({ node, index }))
      .filter(({ node }) => node.categoryType === "expense");

    for (const { node, index } of incomeNodes) {
      expect(sumOutgoingBySource(result.links, index)).toBeCloseTo(node.total ?? 0, 6);
    }
    for (const { node, index } of expenseNodes) {
      expect(sumIncomingByTarget(result.links, index)).toBeCloseTo(node.total ?? 0, 6);
    }
  });
});
