import dayjs, { Dayjs } from "dayjs";
import type { CompanyChoice, RangeFilter } from "./types";

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dayjs(iso).format("YYYY-MM-DD");
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dayjs(iso).format("YYYY-MM-DD HH:mm");
}

export function formatCostUsd(
  value: string | number | null | undefined,
): string {
  if (value == null || value === "") return "$0.0000";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toFixed(4)}`;
}

export function sumCostUsd(values: { total_cost_usd: string }[]): number {
  return values.reduce((acc, row) => {
    const n = Number(row.total_cost_usd);
    return acc + (Number.isFinite(n) ? n : 0);
  }, 0);
}

export function rangeToFilter(
  range: [Dayjs | null, Dayjs | null] | null,
  company: CompanyChoice,
): RangeFilter {
  const [from, to] = range ?? [null, null];
  return {
    from: from ? from.format("YYYY-MM-DD") : undefined,
    to: to ? to.format("YYYY-MM-DD") : undefined,
    company_label: company === "all" ? undefined : company,
  };
}
