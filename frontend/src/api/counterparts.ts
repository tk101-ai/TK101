import api from "./client";

/**
 * 거래처 마스터 API 클라이언트 (재무 모듈 강화 Wave 3 — FE-D).
 *
 * 백엔드: `app/routers/counterparts.py` (BE-C 작업 결과)
 * 별칭 배열·사업자번호·기본 카테고리 매핑·중복 거래처 통합(merge) 지원.
 */

export interface CounterpartRead {
  id: string;
  name: string;
  aliases: string[];
  business_registration_no: string | null;
  default_category_id: string | null;
  default_category_name?: string | null;
  transaction_count?: number;
  created_at?: string;
  updated_at?: string | null;
}

export interface CounterpartCreate {
  name: string;
  aliases?: string[];
  business_registration_no?: string | null;
  default_category_id?: string | null;
}

export interface CounterpartUpdate {
  name?: string;
  aliases?: string[];
  business_registration_no?: string | null;
  default_category_id?: string | null;
}

export interface CounterpartListResponse {
  items: CounterpartRead[];
  total: number;
  page: number;
  page_size: number;
}

export interface CounterpartListParams {
  q?: string;
  page?: number;
  page_size?: number;
  category_id?: string;
}

export interface CounterpartMergeBody {
  source_id: string;
  target_id: string;
}

export interface CounterpartMergeResult {
  merged_transactions: number;
  target_id: string;
  [key: string]: unknown;
}

export interface CounterpartMatchBody {
  name: string;
  business_registration_no?: string;
}

export interface CounterpartMatchResult {
  counterpart_id: string | null;
  match_type: "exact" | "alias" | "registration_no" | "fuzzy" | "none" | string;
}

export async function listCounterparts(
  params: CounterpartListParams = {},
): Promise<CounterpartListResponse> {
  const res = await api.get<CounterpartListResponse>("/api/counterparts", {
    params,
  });
  return res.data;
}

export async function getCounterpart(id: string): Promise<CounterpartRead> {
  const res = await api.get<CounterpartRead>(`/api/counterparts/${id}`);
  return res.data;
}

export async function createCounterpart(
  body: CounterpartCreate,
): Promise<CounterpartRead> {
  const res = await api.post<CounterpartRead>("/api/counterparts", body);
  return res.data;
}

export async function updateCounterpart(
  id: string,
  body: CounterpartUpdate,
): Promise<CounterpartRead> {
  const res = await api.patch<CounterpartRead>(`/api/counterparts/${id}`, body);
  return res.data;
}

export async function deleteCounterpart(id: string): Promise<void> {
  await api.delete(`/api/counterparts/${id}`);
}

export async function mergeCounterparts(
  body: CounterpartMergeBody,
): Promise<CounterpartMergeResult> {
  const res = await api.post<CounterpartMergeResult>(
    "/api/counterparts/merge",
    body,
  );
  return res.data;
}

export async function matchCounterpart(
  body: CounterpartMatchBody,
): Promise<CounterpartMatchResult> {
  const res = await api.post<CounterpartMatchResult>(
    "/api/counterparts/match",
    body,
  );
  return res.data;
}
