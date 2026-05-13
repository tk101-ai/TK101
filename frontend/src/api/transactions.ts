import api from "./client";

/**
 * 거래내역 API 클라이언트 (재무 모듈 강화 Wave 3).
 *
 * 백엔드: `app/routers/transactions.py`
 * Wave 1·2 확장:
 *   - 필터: amount_min, amount_max, category_id, counterpart_id, include_deleted
 *   - 응답 헤더: X-Total-Count (총 건수)
 *   - 모델: category_id, counterpart_id, tags, attachment_url, is_deleted
 *   - 신규 엔드포인트: 수동 등록, 인라인 편집, soft delete/restore,
 *     거래처 자동완성, 매칭 후보, 영수증 첨부
 */

import type { AxiosResponse } from "axios";

export type TransactionType = "deposit" | "withdrawal";
export type MatchStatus = "unmatched" | "matched" | "manual";

export interface Transaction {
  id: string;
  account_id: string;
  transaction_date: string;
  amount: string;
  balance: string | null;
  counterpart_name: string | null;
  description: string | null;
  transaction_type: string;
  matched_transaction_id: string | null;
  match_status: string;
  memo: string | null;
  upload_log_id?: string | null;
  created_at: string;
  // Wave 3 신규 필드
  category_id?: string | null;
  counterpart_id?: string | null;
  tags?: string[] | null;
  attachment_url?: string | null;
  is_deleted: boolean;
}

export interface TransactionFilter {
  account_id?: string;
  date_from?: string;
  date_to?: string;
  transaction_type?: TransactionType;
  match_status?: MatchStatus;
  keyword?: string;
  amount_min?: number;
  amount_max?: number;
  category_id?: string;
  counterpart_id?: string;
  include_deleted?: boolean;
  limit?: number;
  offset?: number;
}

export interface TransactionCreate {
  account_id: string;
  transaction_date: string;
  amount: number;
  transaction_type: TransactionType;
  counterpart_name?: string;
  description?: string;
  balance?: number;
  category_id?: string;
  counterpart_id?: string;
  memo?: string;
  tags?: string[];
}

export interface TransactionUpdate {
  category_id?: string | null;
  counterpart_id?: string | null;
  counterpart_name?: string | null;
  memo?: string | null;
  tags?: string[] | null;
  description?: string | null;
}

export interface CounterpartSuggestion {
  name: string;
  count: number;
  counterpart_id: string | null;
}

export interface AttachmentItem {
  filename: string;
  size: number;
  content_type: string;
  uploaded_at: string;
  url: string;
}

// Category 인터페이스는 `api/categories.ts` 의 `CategoryRead` 를 단일 소스로 사용한다.
// typescript-reviewer H-3 정리 — `api/transactions.ts` 에 중복 정의되어 있던 Category /
// listCategories() 는 제거되었다. 사용처는 `listCategoriesFlat()` 로 마이그레이션한다.

// ---------------------------------------------------------------------------
// 집계 API (재무 대시보드 — Wave 3 FE-C)
// ---------------------------------------------------------------------------

export interface MonthlySummaryRow {
  month: string; // "YYYY-MM"
  deposit_total: string;
  withdrawal_total: string;
  net: string;
  count: number;
}

export interface MonthlySummaryParams {
  from: string; // "YYYY-MM"
  to: string; // "YYYY-MM"
  account_id?: string;
  category_id?: string;
}

export interface TopCounterpartRow {
  counterpart_name: string | null;
  counterpart_id: string | null;
  total_amount: string;
  count: number;
}

export interface TopCounterpartsParams {
  period_from: string; // "YYYY-MM-DD"
  period_to: string; // "YYYY-MM-DD"
  type: TransactionType;
  limit?: number;
}

export interface AccountBalanceRow {
  account_id: string;
  bank_name: string;
  account_number: string;
  account_type: string | null;
  currency: string;
  current_balance: string | null;
  last_synced_at: string | null;
  last_transaction_date: string | null;
}

export async function getMonthlySummary(
  params: MonthlySummaryParams,
): Promise<MonthlySummaryRow[]> {
  const res = await api.get<MonthlySummaryRow[]>(
    "/api/transactions/monthly-summary",
    { params },
  );
  return res.data;
}

export async function getTopCounterparts(
  params: TopCounterpartsParams,
): Promise<TopCounterpartRow[]> {
  const res = await api.get<TopCounterpartRow[]>(
    "/api/transactions/top-counterparts",
    { params },
  );
  return res.data;
}

export async function getAccountBalances(): Promise<AccountBalanceRow[]> {
  const res = await api.get<AccountBalanceRow[]>(
    "/api/transactions/account-balances",
  );
  return res.data;
}

export interface TransactionListResult {
  items: Transaction[];
  total: number;
}

// 매칭 결과 응답 (자동 매칭/정산 트리거)
export interface MatchingRunResponse {
  matched_count: number;
  [key: string]: unknown;
}

// ---------------------------------------------------------------------------
// 목록·CRUD
// ---------------------------------------------------------------------------

/**
 * 거래 목록 조회. X-Total-Count 응답 헤더를 함께 추출하여 반환한다.
 * 백엔드가 헤더를 내려주지 않을 경우 total은 items.length로 fallback.
 */
export async function listTransactions(
  filters: TransactionFilter,
): Promise<TransactionListResult> {
  const res = await api.get<Transaction[]>("/api/transactions", {
    params: filters,
  });
  const totalHeader =
    res.headers?.["x-total-count"] ?? res.headers?.["X-Total-Count"];
  const parsed = typeof totalHeader === "string" ? parseInt(totalHeader, 10) : NaN;
  const total = Number.isFinite(parsed) ? parsed : res.data.length;
  return { items: res.data, total };
}

export async function getTransaction(id: string): Promise<Transaction> {
  const res = await api.get<Transaction>(`/api/transactions/${id}`);
  return res.data;
}

export async function createTransaction(
  body: TransactionCreate,
): Promise<Transaction> {
  const res = await api.post<Transaction>("/api/transactions", body);
  return res.data;
}

export async function updateTransaction(
  id: string,
  body: TransactionUpdate,
): Promise<Transaction> {
  const res = await api.patch<Transaction>(`/api/transactions/${id}`, body);
  return res.data;
}

export async function deleteTransaction(id: string): Promise<void> {
  await api.delete(`/api/transactions/${id}`);
}

export async function restoreTransaction(id: string): Promise<Transaction> {
  const res = await api.post<Transaction>(`/api/transactions/${id}/restore`);
  return res.data;
}

// ---------------------------------------------------------------------------
// 자동완성 / 매칭
// ---------------------------------------------------------------------------

export async function getCounterparts(
  q?: string,
  limit = 20,
): Promise<CounterpartSuggestion[]> {
  const res = await api.get<CounterpartSuggestion[]>(
    "/api/transactions/counterparts",
    { params: { q, limit } },
  );
  return res.data;
}

export async function getMatchCandidates(
  transactionId: string,
  windowDays = 7,
): Promise<Transaction[]> {
  const res = await api.get<Transaction[]>(
    "/api/transactions/matching/candidates",
    { params: { transaction_id: transactionId, window_days: windowDays } },
  );
  return res.data;
}

export async function applyMatch(
  id: string,
  matchedTransactionId: string,
): Promise<Transaction> {
  const res = await api.patch<Transaction>(`/api/transactions/${id}/match`, {
    matched_transaction_id: matchedTransactionId,
  });
  return res.data;
}

export async function removeMatch(id: string): Promise<Transaction> {
  const res = await api.delete<Transaction>(`/api/transactions/${id}/match`);
  return res.data;
}

// ---------------------------------------------------------------------------
// 영수증 첨부
// ---------------------------------------------------------------------------

export async function getAttachments(
  transactionId: string,
): Promise<AttachmentItem[]> {
  const res = await api.get<AttachmentItem[]>(
    `/api/transactions/${transactionId}/attachments`,
  );
  return res.data;
}

export async function uploadAttachment(
  transactionId: string,
  file: File,
): Promise<AttachmentItem> {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post<AttachmentItem>(
    `/api/transactions/${transactionId}/attachments`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return res.data;
}

export async function deleteAttachment(
  transactionId: string,
  filename: string,
): Promise<void> {
  await api.delete(
    `/api/transactions/${transactionId}/attachments/${encodeURIComponent(filename)}`,
  );
}

// ---------------------------------------------------------------------------
// 엑셀 업로드/다운로드 (기존 호환)
// ---------------------------------------------------------------------------

export const downloadExcel = (params: TransactionFilter) =>
  api.get("/api/transactions/download", { params, responseType: "blob" });

export const uploadTransactions = (accountId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/api/uploads/transactions", form, {
    params: { account_id: accountId },
  });
};

export const runMatching = (): Promise<AxiosResponse<MatchingRunResponse>> =>
  api.post<MatchingRunResponse>("/api/matching/run");
export const runReconcile = (): Promise<AxiosResponse<MatchingRunResponse>> =>
  api.post<MatchingRunResponse>("/api/matching/reconcile");

// ---------------------------------------------------------------------------
// 구버전 호환 API (기존 import 경로 보존)
// ---------------------------------------------------------------------------

/** @deprecated listTransactions를 사용하세요. */
export const getTransactions = (params: TransactionFilter) =>
  api.get<Transaction[]>("/api/transactions", { params });

/** @deprecated updateTransaction을 사용하세요. */
export const updateMemo = (id: string, memo: string) =>
  api.patch<Transaction>(`/api/transactions/${id}`, { memo });
