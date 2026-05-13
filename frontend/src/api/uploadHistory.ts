import api from "./client";

/**
 * 업로드 이력 API 클라이언트 (재무 모듈 강화 Wave 3 — FE-D).
 *
 * 백엔드: `app/routers/upload_history.py` (BE-D 작업 결과)
 * 은행 엑셀 import 의 upload_log 단위 이력·에러 행 조회·재처리용 다운로드 URL.
 */

export type UploadStatus = "completed" | "partial" | "failed" | string;

export interface UploadHistoryItem {
  id: string;
  uploaded_at: string;
  file_name: string;
  bank_key: string | null;
  bank_name: string | null;
  account_id: string | null;
  account_label: string | null;
  period_label: string | null;
  imported_count: number;
  duplicate_count: number;
  error_count: number;
  status: UploadStatus;
  uploaded_by_user_id?: string | null;
  uploaded_by_name?: string | null;
}

export interface UploadHistoryListResponse {
  items: UploadHistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface UploadHistoryListParams {
  page?: number;
  page_size?: number;
  account_id?: string;
  status?: UploadStatus;
  from?: string;
  to?: string;
}

export interface UploadHistoryDetail extends UploadHistoryItem {
  errors_preview?: string[];
  metadata?: Record<string, unknown> | null;
}

export interface UploadHistoryErrorRow {
  row_number?: number;
  reason: string;
  raw?: Record<string, unknown> | string | null;
}

export interface UploadHistoryErrorsResponse {
  errors: UploadHistoryErrorRow[];
  total: number;
  download_url?: string | null;
}

export async function listUploadHistory(
  params: UploadHistoryListParams = {},
): Promise<UploadHistoryListResponse> {
  const res = await api.get<UploadHistoryListResponse>("/api/upload-history", {
    params,
  });
  return res.data;
}

export async function getUploadHistory(
  id: string,
): Promise<UploadHistoryDetail> {
  const res = await api.get<UploadHistoryDetail>(`/api/upload-history/${id}`);
  return res.data;
}

export async function getUploadHistoryErrors(
  id: string,
): Promise<UploadHistoryErrorsResponse> {
  const res = await api.get<UploadHistoryErrorsResponse>(
    `/api/upload-history/${id}/errors`,
  );
  return res.data;
}
