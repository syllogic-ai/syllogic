export type CsvDelimiter = "," | ";" | "\t";

export type AmountFormat = "AUTO" | "DOT_DECIMAL" | "COMMA_DECIMAL";
export type InferredAmountFormat = Exclude<AmountFormat, "AUTO"> | "AMBIGUOUS";

export interface ParsedDelimitedText {
  headers: string[];
  rows: string[][];
}

interface ParsedNumericToken {
  negative: boolean;
  token: string;
}

export function detectCsvDelimiter(fileContent: string): CsvDelimiter {
  const normalized = normalizeLineEndings(fileContent);
  const lines = normalized
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .slice(0, 10);

  if (lines.length === 0) {
    return ",";
  }

  const candidates: CsvDelimiter[] = [",", ";", "\t"];
  let bestDelimiter: CsvDelimiter = ",";
  let bestScore = Number.NEGATIVE_INFINITY;

  for (const delimiter of candidates) {
    const rowLengths = lines.map((line) => parseDelimitedLine(line, delimiter).length);
    const headerLength = rowLengths[0] ?? 0;
    const matchingRows = rowLengths.filter((length) => length === headerLength && length > 1).length;
    const uniqueLengths = new Set(rowLengths).size;
    const score = (headerLength > 1 ? 100 : 0) + (matchingRows * 10) - uniqueLengths;

    if (score > bestScore) {
      bestScore = score;
      bestDelimiter = delimiter;
    }
  }

  return bestDelimiter;
}

export function parseDelimitedText(fileContent: string, delimiter: CsvDelimiter): ParsedDelimitedText {
  const normalized = normalizeLineEndings(fileContent);
  const lines = normalized
    .split("\n")
    .filter((line) => line.trim().length > 0);

  if (lines.length === 0) {
    return { headers: [], rows: [] };
  }

  const headers = parseDelimitedLine(lines[0], delimiter);
  const rows = lines.slice(1).map((line) => parseDelimitedLine(line, delimiter));

  return { headers, rows };
}

export function inferAmountFormat(samples: Array<string | null | undefined>): InferredAmountFormat {
  let dotEvidence = 0;
  let commaEvidence = 0;

  for (const sample of samples) {
    const parsed = parseNumericToken(sample);
    if (!parsed) {
      continue;
    }

    const { token } = parsed;
    const dotCount = countOccurrences(token, ".");
    const commaCount = countOccurrences(token, ",");

    if (dotCount > 0 && commaCount > 0) {
      if (token.lastIndexOf(".") > token.lastIndexOf(",")) {
        dotEvidence += 1;
      } else {
        commaEvidence += 1;
      }
      continue;
    }

    const separator = dotCount > 0 ? "." : commaCount > 0 ? "," : null;
    if (!separator) {
      continue;
    }

    const digitsAfter = token.length - token.lastIndexOf(separator) - 1;
    if (digitsAfter === 0 || digitsAfter === 3) {
      continue;
    }

    if (separator === ".") {
      dotEvidence += 1;
    } else {
      commaEvidence += 1;
    }
  }

  if (dotEvidence > 0 && commaEvidence === 0) {
    return "DOT_DECIMAL";
  }

  if (commaEvidence > 0 && dotEvidence === 0) {
    return "COMMA_DECIMAL";
  }

  return "AMBIGUOUS";
}

export function parseLocalizedNumber(
  raw: string | null | undefined,
  options: {
    amountFormat?: AmountFormat;
    inferredFormat?: InferredAmountFormat;
    allowGroupedIntegersWhenAmbiguous?: boolean;
  } = {}
): number | null {
  const parsed = parseNumericToken(raw);
  if (!parsed) {
    return null;
  }

  const { negative, token } = parsed;
  const dotCount = countOccurrences(token, ".");
  const commaCount = countOccurrences(token, ",");

  let normalized: string | null = null;

  if (dotCount > 0 && commaCount > 0) {
    const decimalSeparator = token.lastIndexOf(".") > token.lastIndexOf(",") ? "." : ",";
    normalized = normalizeWithDecimalSeparator(token, decimalSeparator);
  } else if (dotCount > 0 || commaCount > 0) {
    const separator = dotCount > 0 ? "." : ",";
    const resolvedFormat = resolveAmountFormat(options.amountFormat, options.inferredFormat);

    if (resolvedFormat) {
      normalized = normalizeWithDecimalSeparator(
        token,
        resolvedFormat === "DOT_DECIMAL" ? "." : ","
      );
    } else {
      const digitsAfter = token.length - token.lastIndexOf(separator) - 1;
      if (digitsAfter === 0 || digitsAfter === 3) {
        if (options.allowGroupedIntegersWhenAmbiguous && digitsAfter === 3) {
          normalized = normalizeGroupedInteger(token);
        } else {
          return null;
        }
      } else {
        normalized = normalizeWithDecimalSeparator(token, separator);
      }
    }
  } else {
    normalized = token;
  }

  if (!normalized) {
    return null;
  }

  const numericValue = Number(normalized);
  if (!Number.isFinite(numericValue)) {
    return null;
  }

  return negative ? -numericValue : numericValue;
}

function normalizeLineEndings(value: string): string {
  return value.replace(/\r\n/g, "\n").replace(/\r/g, "\n");
}

function parseDelimitedLine(line: string, delimiter: CsvDelimiter): string[] {
  const cells: string[] = [];
  let current = "";
  let inQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];

    if (char === "\"") {
      const nextChar = line[index + 1];
      if (inQuotes && nextChar === "\"") {
        current += "\"";
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === delimiter && !inQuotes) {
      cells.push(current.trim());
      current = "";
      continue;
    }

    current += char;
  }

  cells.push(current.trim());
  return cells;
}

function parseNumericToken(raw: string | null | undefined): ParsedNumericToken | null {
  if (!raw) {
    return null;
  }

  let value = raw
    .trim()
    .replace(/\u2212/g, "-")
    .replace(/[\u2012\u2013\u2014]/g, "-");

  if (!value) {
    return null;
  }

  value = value.replace(/[^\d.,'’()\-\s\u00A0\u202F]/gu, "");
  value = value.trim();

  if (!value) {
    return null;
  }

  let negative = false;
  if (/^\(.*\)$/.test(value)) {
    negative = true;
    value = value.slice(1, -1);
  }

  if (value.startsWith("-")) {
    negative = true;
    value = value.slice(1);
  }

  if (value.endsWith("-")) {
    negative = true;
    value = value.slice(0, -1);
  }

  value = value
    .replace(/[()]/g, "")
    .replace(/['’\s\u00A0\u202F]/g, "")
    .trim();

  if (!/\d/.test(value)) {
    return null;
  }

  return { negative, token: value };
}

function countOccurrences(value: string, search: "." | ","): number {
  return value.split(search).length - 1;
}

function resolveAmountFormat(
  amountFormat: AmountFormat | undefined,
  inferredFormat: InferredAmountFormat | undefined
): Exclude<AmountFormat, "AUTO"> | null {
  if (amountFormat && amountFormat !== "AUTO") {
    return amountFormat;
  }

  if (inferredFormat && inferredFormat !== "AMBIGUOUS") {
    return inferredFormat;
  }

  return null;
}

function normalizeWithDecimalSeparator(
  token: string,
  decimalSeparator: "." | ","
): string | null {
  const decimalIndex = token.lastIndexOf(decimalSeparator);
  let normalized = "";

  for (let index = 0; index < token.length; index += 1) {
    const char = token[index];

    if (/\d/.test(char)) {
      normalized += char;
      continue;
    }

    if (char === "." || char === ",") {
      if (char === decimalSeparator && index === decimalIndex) {
        normalized += ".";
      }
      continue;
    }

    return null;
  }

  if (!normalized || normalized === ".") {
    return null;
  }

  return normalized;
}

function normalizeGroupedInteger(token: string): string | null {
  let normalized = "";

  for (const char of token) {
    if (/\d/.test(char)) {
      normalized += char;
      continue;
    }

    if (char === "." || char === ",") {
      continue;
    }

    return null;
  }

  return normalized || null;
}
