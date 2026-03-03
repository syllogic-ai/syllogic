export type IncomeExpenseGrouping = "day" | "week" | "month";

interface DailyIncomeExpensePoint {
  date: string;
  income: number;
  expenses: number;
}

export interface IncomeExpenseChartPoint {
  month: string;
  monthDate: string;
  income: number;
  expenses: number;
  tooltipLabel: string;
}

interface BuildIncomeExpenseBucketsInput {
  startDate: Date;
  endDate: Date;
  dailyData: DailyIncomeExpensePoint[];
  grouping?: IncomeExpenseGrouping;
}

const MS_PER_DAY = 86_400_000;

const shortMonthDayFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
});

const shortMonthYearFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  year: "2-digit",
});

const longMonthYearFormatter = new Intl.DateTimeFormat("en-US", {
  month: "long",
  year: "numeric",
});

const mediumDateFormatter = new Intl.DateTimeFormat("en-US", {
  month: "short",
  day: "numeric",
  year: "numeric",
});

function startOfDay(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate());
}

function startOfMonth(date: Date): Date {
  return new Date(date.getFullYear(), date.getMonth(), 1);
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function toIsoDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(
    date.getDate()
  ).padStart(2, "0")}`;
}

function parseIsoDate(isoDate: string): Date {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function toUtcDayValue(date: Date): number {
  return Math.floor(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / MS_PER_DAY);
}

function getInclusiveDayCount(startDate: Date, endDate: Date): number {
  return toUtcDayValue(endDate) - toUtcDayValue(startDate) + 1;
}

function buildDailyMap(dailyData: DailyIncomeExpensePoint[]): Map<string, { income: number; expenses: number }> {
  return new Map(
    dailyData.map((point) => [
      point.date,
      {
        income: point.income,
        expenses: point.expenses,
      },
    ])
  );
}

export function resolveIncomeExpenseGrouping(
  startDate: Date,
  endDate: Date
): IncomeExpenseGrouping {
  const rangeStart = startOfDay(startDate);
  const rangeEnd = startOfDay(endDate);
  const dayCount = getInclusiveDayCount(rangeStart, rangeEnd);

  if (dayCount <= 7) {
    return "day";
  }

  if (dayCount <= 31) {
    return "week";
  }

  return "month";
}

function buildDailyBuckets(
  rangeStart: Date,
  totalDays: number,
  dailyMap: Map<string, { income: number; expenses: number }>
): IncomeExpenseChartPoint[] {
  const buckets: IncomeExpenseChartPoint[] = [];

  for (let dayOffset = 0; dayOffset < totalDays; dayOffset += 1) {
    const currentDate = addDays(rangeStart, dayOffset);
    const isoDate = toIsoDate(currentDate);
    const values = dailyMap.get(isoDate);

    buckets.push({
      month: shortMonthDayFormatter.format(currentDate),
      monthDate: isoDate,
      income: values?.income ?? 0,
      expenses: values?.expenses ?? 0,
      tooltipLabel: mediumDateFormatter.format(currentDate),
    });
  }

  return buckets;
}

function buildWeeklyBuckets(
  rangeStart: Date,
  rangeEnd: Date,
  totalDays: number,
  dailyMap: Map<string, { income: number; expenses: number }>
): IncomeExpenseChartPoint[] {
  const buckets: IncomeExpenseChartPoint[] = [];

  for (let dayOffset = 0; dayOffset < totalDays; dayOffset += 7) {
    const bucketStart = addDays(rangeStart, dayOffset);
    const bucketEndOffset = Math.min(dayOffset + 6, totalDays - 1);
    const bucketEnd = addDays(rangeStart, bucketEndOffset);
    const clampedBucketEnd = bucketEnd > rangeEnd ? rangeEnd : bucketEnd;

    let income = 0;
    let expenses = 0;

    for (let offset = dayOffset; offset <= bucketEndOffset; offset += 1) {
      const isoDate = toIsoDate(addDays(rangeStart, offset));
      const values = dailyMap.get(isoDate);
      if (values) {
        income += values.income;
        expenses += values.expenses;
      }
    }

    buckets.push({
      month: shortMonthDayFormatter.format(bucketStart),
      monthDate: toIsoDate(bucketStart),
      income,
      expenses,
      tooltipLabel: `${mediumDateFormatter.format(bucketStart)} - ${mediumDateFormatter.format(
        clampedBucketEnd
      )}`,
    });
  }

  return buckets;
}

function buildMonthlyBuckets(
  rangeStart: Date,
  rangeEnd: Date,
  dailyData: DailyIncomeExpensePoint[]
): IncomeExpenseChartPoint[] {
  const monthTotals = new Map<string, { income: number; expenses: number }>();

  for (const row of dailyData) {
    const rowDate = parseIsoDate(row.date);
    const monthDate = new Date(rowDate.getFullYear(), rowDate.getMonth(), 1);
    const monthKey = toIsoDate(monthDate);
    const existing = monthTotals.get(monthKey);
    if (existing) {
      existing.income += row.income;
      existing.expenses += row.expenses;
    } else {
      monthTotals.set(monthKey, { income: row.income, expenses: row.expenses });
    }
  }

  const buckets: IncomeExpenseChartPoint[] = [];
  let currentMonth = startOfMonth(rangeStart);
  const finalMonth = startOfMonth(rangeEnd);

  while (currentMonth <= finalMonth) {
    const monthKey = toIsoDate(currentMonth);
    const values = monthTotals.get(monthKey);
    buckets.push({
      month: shortMonthYearFormatter.format(currentMonth),
      monthDate: monthKey,
      income: values?.income ?? 0,
      expenses: values?.expenses ?? 0,
      tooltipLabel: longMonthYearFormatter.format(currentMonth),
    });

    currentMonth = new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1, 1);
  }

  return buckets;
}

export function buildIncomeExpenseBuckets({
  startDate,
  endDate,
  dailyData,
  grouping,
}: BuildIncomeExpenseBucketsInput): IncomeExpenseChartPoint[] {
  const rangeStart = startOfDay(startDate);
  const rangeEnd = startOfDay(endDate);

  if (toUtcDayValue(rangeEnd) < toUtcDayValue(rangeStart)) {
    return [];
  }

  const resolvedGrouping = grouping ?? resolveIncomeExpenseGrouping(rangeStart, rangeEnd);
  const totalDays = getInclusiveDayCount(rangeStart, rangeEnd);
  const dailyMap = buildDailyMap(dailyData);

  if (resolvedGrouping === "day") {
    return buildDailyBuckets(rangeStart, totalDays, dailyMap);
  }

  if (resolvedGrouping === "week") {
    return buildWeeklyBuckets(rangeStart, rangeEnd, totalDays, dailyMap);
  }

  return buildMonthlyBuckets(rangeStart, rangeEnd, dailyData);
}
