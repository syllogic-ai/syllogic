import { describe, expect, it } from "vitest";
import {
  detectCsvDelimiter,
  inferAmountFormat,
  parseDelimitedText,
  parseLocalizedNumber,
} from "@/lib/import/parsing";

describe("import parsing helpers", () => {
  it("detects semicolon-delimited files with comma decimals", () => {
    const content = [
      "Date;Amount;Description",
      "2026-03-01;1.234,56;Groceries",
      "2026-03-02;-12,34;Coffee",
    ].join("\n");

    expect(detectCsvDelimiter(content)).toBe(";");
    expect(parseDelimitedText(content, ";")).toEqual({
      headers: ["Date", "Amount", "Description"],
      rows: [
        ["2026-03-01", "1.234,56", "Groceries"],
        ["2026-03-02", "-12,34", "Coffee"],
      ],
    });
  });

  it("respects quoted fields when parsing delimited text", () => {
    const content = [
      "Date;Amount;Description",
      '2026-03-01;"1.234,56";"Groceries; weekly"',
    ].join("\n");

    expect(parseDelimitedText(content, ";").rows[0]).toEqual([
      "2026-03-01",
      "1.234,56",
      "Groceries; weekly",
    ]);
  });

  it("infers dot-decimal format from file-wide samples", () => {
    expect(inferAmountFormat(["1,234.56", "-12.34", "$3,250.00"])).toBe("DOT_DECIMAL");
  });

  it("infers comma-decimal format from file-wide samples", () => {
    expect(inferAmountFormat(["1.234,56", "-12,34", "€ 3.250,00"])).toBe("COMMA_DECIMAL");
  });

  it("returns ambiguous when the file does not disambiguate decimals", () => {
    expect(inferAmountFormat(["1,234", "9,876", "123"])).toBe("AMBIGUOUS");
    expect(parseLocalizedNumber("1,234", { amountFormat: "AUTO", inferredFormat: "AMBIGUOUS" })).toBeNull();
  });

  it("parses dot-decimal values with grouping and currency markers", () => {
    expect(parseLocalizedNumber("$1,234.56")).toBe(1234.56);
    expect(parseLocalizedNumber("1'234.56")).toBe(1234.56);
    expect(parseLocalizedNumber("(1,234.56)")).toBe(-1234.56);
  });

  it("parses comma-decimal values with spaces, nbsp, and trailing minus", () => {
    expect(parseLocalizedNumber("€ 1.234,56")).toBe(1234.56);
    expect(parseLocalizedNumber("1 234,56")).toBe(1234.56);
    expect(parseLocalizedNumber("1\u00A0234,56")).toBe(1234.56);
    expect(parseLocalizedNumber("123,45-")).toBe(-123.45);
  });

  it("uses explicit amount format overrides for ambiguous values", () => {
    expect(parseLocalizedNumber("1,234", { amountFormat: "DOT_DECIMAL" })).toBe(1234);
    expect(parseLocalizedNumber("1,234", { amountFormat: "COMMA_DECIMAL" })).toBe(1.234);
    expect(parseLocalizedNumber("1.234", { amountFormat: "COMMA_DECIMAL" })).toBe(1234);
    expect(parseLocalizedNumber("1.234", { amountFormat: "DOT_DECIMAL" })).toBe(1.234);
  });

  it("parses fee and balance style values through the same helper", () => {
    expect(parseLocalizedNumber("9,99", { amountFormat: "COMMA_DECIMAL" })).toBe(9.99);
    expect(parseLocalizedNumber("12.345,67", { amountFormat: "COMMA_DECIMAL" })).toBe(12345.67);
  });
});
