import api from "./client";

/**
 * 신사업유통 대시보드 API 클라이언트 (T9 Phase E-1).
 *
 * 백엔드: `app/routers/distribution_dashboard.py`
 *
 * 모든 GET 엔드포인트는 admin 권한 필요. 기간 필터(`from`/`to`)는 옵션이며
 * `YYYY-MM-DD` 문자열로 전송. 카테고리/브랜드 분포는 시점 데이터라 기간 필터 X.
 */

const BASE = "/api/distribution/dashboard";

export interface OverviewOut {
  total_kr_purchase: number;
  total_vn_inventory_move: number;
  total_vn_sales: number;
  total_deposit_req: number;
  total_account_deposit: number;
  total_cash_deposit: number;
  product_count: number;
  total_purchase_qty: number;
  total_stock_qty: number;
  session_count: number;
  approved_count: number;
  sent_count: number;
  failed_count: number;
  total_llm_cost_usd: number;
}

export interface WeeklyTrendItem {
  period_start: string; // ISO date YYYY-MM-DD
  period_label: string;
  kr_purchase: number;
  vn_inventory_move: number;
  vn_sales_completed: number;
  deposit_total: number;
}

export interface CategoryDistItem {
  category: string;
  product_count: number;
  total_purchase_qty: number;
  total_stock_qty: number;
}

export interface BrandDistItem {
  brand: string;
  product_count: number;
  total_stock_qty: number;
}

export type DashboardSessionStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "sending"
  | "sent"
  | "failed";

export interface StatusBreakdownItem {
  status: DashboardSessionStatus | string;
  count: number;
}

export interface SendSuccessRateOut {
  total_attempts: number;
  success_count: number;
  failed_count: number;
  success_rate: number; // 0.0 ~ 1.0
}

interface DateRangeParams {
  from?: string;
  to?: string;
}

function rangeParams(from?: string, to?: string): DateRangeParams {
  const params: DateRangeParams = {};
  if (from) params.from = from;
  if (to) params.to = to;
  return params;
}

export async function getOverview(
  from?: string,
  to?: string,
): Promise<OverviewOut> {
  const res = await api.get<OverviewOut>(`${BASE}/overview`, {
    params: rangeParams(from, to),
  });
  return res.data;
}

export async function getWeeklyTrends(
  from?: string,
  to?: string,
): Promise<WeeklyTrendItem[]> {
  const res = await api.get<WeeklyTrendItem[]>(`${BASE}/weekly-trends`, {
    params: rangeParams(from, to),
  });
  return res.data;
}

export async function getCategoryDist(): Promise<CategoryDistItem[]> {
  const res = await api.get<CategoryDistItem[]>(`${BASE}/category-distribution`);
  return res.data;
}

export async function getBrandDist(topN = 10): Promise<BrandDistItem[]> {
  const res = await api.get<BrandDistItem[]>(`${BASE}/brand-distribution`, {
    params: { top_n: topN },
  });
  return res.data;
}

export async function getSessionBreakdown(
  from?: string,
  to?: string,
): Promise<StatusBreakdownItem[]> {
  const res = await api.get<StatusBreakdownItem[]>(
    `${BASE}/session-status-breakdown`,
    { params: rangeParams(from, to) },
  );
  return res.data;
}

export async function getSendSuccessRate(
  from?: string,
  to?: string,
): Promise<SendSuccessRateOut> {
  const res = await api.get<SendSuccessRateOut>(`${BASE}/send-success-rate`, {
    params: rangeParams(from, to),
  });
  return res.data;
}

// 세션 상태 라벨/색 매핑 (대시보드 차트에서 사용).
// SessionsPage 와 동일한 매핑이지만 의존 방향을 끊기 위해 자체 정의.
export const DASHBOARD_STATUS_LABEL: Record<string, string> = {
  pending: "검수 대기",
  approved: "승인됨",
  rejected: "거부됨",
  sending: "송신 중",
  sent: "송신 완료",
  failed: "실패",
};

export const DASHBOARD_STATUS_COLOR: Record<string, string> = {
  pending: "#faad14",
  approved: "#1677ff",
  rejected: "#8c8c8c",
  sending: "#13c2c2",
  sent: "#52c41a",
  failed: "#ff4d4f",
};
