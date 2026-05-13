import api from "./client";

/**
 * 은행 거래내역 자동 임포트 API 클라이언트 (재무 모듈 강화 Wave 3 — FE-D).
 *
 * 백엔드: `app/routers/bank_import.py` (BE-B 작업 결과)
 * 흐름: 어댑터 목록 조회 → 파일 업로드 후 preview → confirm 으로 실제 저장.
 *
 * 주의: Wave 5 에서 main.py 라우터 등록이 완료되기 전까지는 호출 시 404 가
 *       돌아온다. 페이지에서는 message.error 로 안내한다.
 */

export interface BankAdapter {
  bank_key: string;
  bank_name: string;
  priority: number;
}

export interface SimilarAccount {
  account_id: string;
  account_number: string;
  account_holder: string | null;
  bank_name: string | null;
  similarity: number;
}

export interface ImportAccountMeta {
  bank_key?: string | null;
  bank_name?: string | null;
  account_number?: string | null;
  account_holder?: string | null;
  business_registration_no?: string | null;
  currency?: string | null;
  account_type?: string | null;
  account_label?: string | null;
  period_label?: string | null;
  period_year?: number | null;
  period_quarter?: number | null;
  [key: string]: unknown;
}

export interface ImportPreviewOut {
  file_name: string;
  adapter_detected: string | null;
  bank_name: string | null;
  account_meta: ImportAccountMeta;
  existing_account_id: string | null;
  similar_accounts: SimilarAccount[];
  transaction_count: number;
  duplicate_count_estimate: number;
  parse_warnings: string[];
  parse_errors: string[];
}

export type ImportDuplicatePolicy = "skip" | "overwrite";

/** 신규 계좌 등록 페이로드 — backend `schemas/account.py::AccountCreate` 와 일치. */
export interface AccountCreatePayload {
  bank_name: string;
  account_number: string;
  account_holder: string;
  business_registration_no?: string | null;
  account_type?: string | null;
  currency?: string;
  alias?: string | null;
  account_label?: string | null;
}

export interface ConfirmPayload {
  account_id?: string;
  /** 신규 계좌 등록 시 AccountCreate 객체. 미리보기 메타를 그대로 채워 보낸다. */
  create_account?: AccountCreatePayload;
  on_duplicate?: ImportDuplicatePolicy;
}

export interface ImportErrorRow {
  row_number?: number;
  reason: string;
  raw?: Record<string, unknown> | string | null;
}

export interface ImportResultOut {
  upload_log_id: string;
  account_id: string | null;
  bank_key: string | null;
  imported_count: number;
  duplicate_count: number;
  error_count: number;
  status: string;
  errors: ImportErrorRow[];
}

/** 지원되는 은행 어댑터 목록 (우선순위 정렬). */
export async function getAdapters(): Promise<BankAdapter[]> {
  const res = await api.get<BankAdapter[]>("/api/bank-import/adapters");
  return res.data;
}

/**
 * 업로드 파일을 분석해 미리보기 정보를 반환한다. 실제 저장은 일어나지 않음.
 */
export async function previewImport(file: File): Promise<ImportPreviewOut> {
  const form = new FormData();
  form.append("file", file);
  const res = await api.post<ImportPreviewOut>(
    "/api/bank-import/preview",
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return res.data;
}

/**
 * 미리보기 후 사용자 선택에 따라 실제 import 를 수행한다.
 * payload 는 JSON 문자열로 별도 form field 에 담아 전송한다.
 */
export async function confirmImport(
  file: File,
  payload: ConfirmPayload,
): Promise<ImportResultOut> {
  const form = new FormData();
  form.append("file", file);
  form.append("payload", JSON.stringify(payload));
  const res = await api.post<ImportResultOut>(
    "/api/bank-import/confirm",
    form,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return res.data;
}
