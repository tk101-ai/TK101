import api from "./client";

/**
 * 신사업유통 분석 페이지 API 클라이언트 (T9 Phase E-4).
 *
 * 백엔드: `app/routers/distribution_analytics.py`
 *
 * 대시보드(`api/distribution.ts` 의 일부) 와는 분리된 별도 모듈.
 * 분석 페이지는 운영자가 Claude 비용 추세, 송신 실패 원인, 과거 메시지를
 * 검색·디버깅하는 용도.
 *
 * 응답의 `total_cost_usd` 는 Decimal → JSON 직렬화로 string 형태로 도착함.
 * UI 에서 `Number(...)` 변환 후 포맷팅.
 */

const BASE = "/api/distribution/analytics";

export interface CostByDayItem {
  date: string;
  total_cost_usd: string;
  session_count: number;
}

export interface CostByPersonaItem {
  persona_id: string;
  account_label: string;
  total_cost_usd: string;
  session_count: number;
}

export interface SendFailureItem {
  error_code: string;
  count: number;
  last_attempted_at: string;
}

export interface MessageSearchItem {
  message_id: string;
  session_id: string;
  scenario_name: string;
  sender_account_label: string;
  content: string;
  sent_at: string | null;
  status: string;
}

/** 빈 문자열 제거 후 query string 생성. axios `params` 는 undefined 만 자동 제거. */
function buildParams(
  from?: string,
  to?: string,
  extra?: Record<string, string | number | undefined>,
): Record<string, string | number> {
  const params: Record<string, string | number> = {};
  if (from) params.from = from;
  if (to) params.to = to;
  if (extra) {
    for (const [k, v] of Object.entries(extra)) {
      if (v !== undefined && v !== "") params[k] = v;
    }
  }
  return params;
}

export async function getCostByDay(
  from?: string,
  to?: string,
): Promise<CostByDayItem[]> {
  const res = await api.get<CostByDayItem[]>(`${BASE}/cost-by-day`, {
    params: buildParams(from, to),
  });
  return res.data;
}

export async function getCostByPersona(
  from?: string,
  to?: string,
): Promise<CostByPersonaItem[]> {
  const res = await api.get<CostByPersonaItem[]>(`${BASE}/cost-by-persona`, {
    params: buildParams(from, to),
  });
  return res.data;
}

export async function getSendFailures(
  from?: string,
  to?: string,
): Promise<SendFailureItem[]> {
  const res = await api.get<SendFailureItem[]>(`${BASE}/send-failures`, {
    params: buildParams(from, to),
  });
  return res.data;
}

export async function getSessionStatusCounts(
  from?: string,
  to?: string,
): Promise<Record<string, number>> {
  const res = await api.get<Record<string, number>>(
    `${BASE}/session-status-counts`,
    { params: buildParams(from, to) },
  );
  return res.data;
}

export async function searchMessages(
  q: string,
  from?: string,
  to?: string,
  limit?: number,
): Promise<MessageSearchItem[]> {
  const res = await api.get<MessageSearchItem[]>(`${BASE}/search-messages`, {
    params: buildParams(from, to, { q, limit }),
  });
  return res.data;
}
