import api from "./client";

/** 집계 기준 — 일별 / 사용자별 / 종류별. */
export type UsageGroupBy = "day" | "user" | "kind";

/** kind 필터 — 양식 작성(fill) / 문서 생성(generate) / 전체. */
export type UsageKindFilter = "fill" | "generate" | "all";

export interface UsageRow {
  bucket: string;
  kind: string | null;
  job_count: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
}

export interface UsageTotals {
  job_count: number;
  tokens_in: number;
  tokens_out: number;
  cost_usd: number;
}

export interface UsageResponse {
  group_by: UsageGroupBy;
  start: string;
  end: string;
  rows: UsageRow[];
  totals: UsageTotals;
}

export interface UsageQuery {
  start?: string; // YYYY-MM-DD
  end?: string; // YYYY-MM-DD
  group_by?: UsageGroupBy;
  kind?: UsageKindFilter;
}

/** 관리자 전용 문서 토큰/비용 사용량 집계. require_admin(403). */
export async function getDocumentsUsage(
  q: UsageQuery = {},
): Promise<UsageResponse> {
  const params: Record<string, string> = {};
  if (q.start) params.start = q.start;
  if (q.end) params.end = q.end;
  if (q.group_by) params.group_by = q.group_by;
  if (q.kind) params.kind = q.kind;
  const res = await api.get<UsageResponse>("/api/documents/admin/usage", {
    params,
  });
  return res.data;
}
