import api from "./client";

/**
 * 체험단 후기 중→한 번역 API 클라이언트 (업무개선요구사항 #17).
 *
 * 백엔드: `app/routers/review_translation.py`
 * 권한: `review_translation` 모듈 — admin + marketing_1.
 */

export interface ReviewTranslation {
  id: string;
  created_at: string;
  updated_at: string | null;
  source_text: string;
  translated_text: string;
  campaign: string | null;
  reviewer_name: string | null;
  platform: string | null;
  model_used: string;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  created_by_id: string | null;
}

export interface ReviewTranslationCreate {
  source_text: string;
  campaign?: string | null;
  reviewer_name?: string | null;
  platform?: string | null;
}

export interface ReviewTranslationUpdate {
  translated_text?: string;
  campaign?: string | null;
  reviewer_name?: string | null;
  platform?: string | null;
}

export interface ReviewTranslationListResponse {
  items: ReviewTranslation[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReviewTranslationListParams {
  page?: number;
  page_size?: number;
  search?: string;
  campaign?: string;
}

export async function translateAndSave(
  body: ReviewTranslationCreate,
): Promise<ReviewTranslation> {
  const res = await api.post<ReviewTranslation>(
    "/api/review-translations/translate",
    body,
  );
  return res.data;
}

export async function listReviewTranslations(
  params?: ReviewTranslationListParams,
): Promise<ReviewTranslationListResponse> {
  const res = await api.get<ReviewTranslationListResponse>(
    "/api/review-translations",
    { params },
  );
  return res.data;
}

export async function getReviewTranslation(
  id: string,
): Promise<ReviewTranslation> {
  const res = await api.get<ReviewTranslation>(
    `/api/review-translations/${id}`,
  );
  return res.data;
}

export async function updateReviewTranslation(
  id: string,
  body: ReviewTranslationUpdate,
): Promise<ReviewTranslation> {
  const res = await api.put<ReviewTranslation>(
    `/api/review-translations/${id}`,
    body,
  );
  return res.data;
}

export async function deleteReviewTranslation(id: string): Promise<void> {
  await api.delete(`/api/review-translations/${id}`);
}
