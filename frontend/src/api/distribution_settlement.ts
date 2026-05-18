import api from "./client";

/**
 * 신사업유통 정산 (자금 흐름) API 클라이언트 (T9 Phase F-C).
 *
 * 백엔드: `app/routers/distribution_settlement.py`
 *
 * 모든 GET 엔드포인트는 admin 권한 필요. 기간 필터(`from`/`to`)는 옵션이며
 * `YYYY-MM-DD` 문자열로 전송. `company_label` 은 옵션(미지정 시 전체).
 *
 * 데이터 의미:
 * - 매입: kr_purchase + vn_inventory_move + vn_sales_completed
 * - 입금요청: 자동계산 3종 합계 (KR매입×40% + VN재고×30% + VN매출×30%)
 * - 실 입금: account_deposit + cash_deposit
 * - 외상잔고: 시트 정의 — kr_purchase - 실 입금
 * - 이행률: 실 입금 / 입금요청 (0.0~1.0)
 */

const BASE = "/api/distribution/settlement";

export interface CashFlowItem {
  period_label: string;
  period_start: string; // ISO YYYY-MM-DD
  period_end: string; // ISO YYYY-MM-DD
  company_label: string;
  kr_purchase: number;
  vn_inventory_move: number;
  vn_sales_completed: number;
  kr_purchase_deposit_req: number;
  vn_inventory_deposit_req: number;
  vn_sales_deposit_req: number;
  deposit_req_total: number;
  account_deposit: number;
  cash_deposit: number;
  deposit_total: number;
  outstanding_balance: number;
  fulfillment_rate: number; // 0.0 ~ 1.0
}

export interface SettlementSummary {
  company_count: number;
  period_count: number;
  total_kr_purchase: number;
  total_vn_inventory_move: number;
  total_vn_sales: number;
  total_deposit_req: number;
  total_deposit_received: number;
  total_outstanding: number;
  fulfillment_rate: number; // 0.0 ~ 1.0
  latest_period_label: string | null;
}

export interface ByCompanyItem {
  company_label: string;
  period_count: number;
  total_kr_purchase: number;
  total_deposit_req: number;
  total_deposit_received: number;
  total_outstanding: number;
  fulfillment_rate: number; // 0.0 ~ 1.0
}

interface SettlementParams {
  from?: string;
  to?: string;
  company_label?: string;
}

function buildParams(params?: {
  from?: string;
  to?: string;
  company_label?: string;
}): SettlementParams {
  const out: SettlementParams = {};
  if (params?.from) out.from = params.from;
  if (params?.to) out.to = params.to;
  if (params?.company_label) out.company_label = params.company_label;
  return out;
}

export async function getCashFlow(params?: {
  from?: string;
  to?: string;
  company_label?: string;
}): Promise<CashFlowItem[]> {
  const res = await api.get<CashFlowItem[]>(`${BASE}/cash-flow`, {
    params: buildParams(params),
  });
  return res.data;
}

export async function getSettlementSummary(params?: {
  from?: string;
  to?: string;
  company_label?: string;
}): Promise<SettlementSummary> {
  const res = await api.get<SettlementSummary>(`${BASE}/summary`, {
    params: buildParams(params),
  });
  return res.data;
}

export async function getByCompany(params?: {
  from?: string;
  to?: string;
}): Promise<ByCompanyItem[]> {
  const res = await api.get<ByCompanyItem[]>(`${BASE}/by-company`, {
    params: buildParams(params),
  });
  return res.data;
}

export async function listSettlementCompanies(): Promise<string[]> {
  const res = await api.get<{ items: string[] }>(`${BASE}/companies`);
  return res.data.items;
}
