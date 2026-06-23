import api from "./client";
import { triggerBlobDownload } from "../utils/download";

export type Platform = "facebook" | "instagram" | "twitter" | "youtube" | "weibo";
export type Language = "en" | "zh" | "ja";
// 게시물 구분(카테고리) — 수동 태그. SNS API 로는 못 긁어오는 분류 축. (마이그레이션 035)
export type PostCategory = "행사" | "기획" | "정책" | "이벤트" | "기타";

export interface SnsAccount {
  id: string;
  platform: Platform;
  language: Language;
  handle: string | null;
  page_url: string | null;
  external_id: string | null;
  is_active: boolean;
  client: string | null;
  created_at: string;
}

export interface SnsPost {
  id: string;
  account_id: string;
  posted_at: string;
  title: string | null;
  content_type: string | null;
  producer: string | null;
  view_count: number | null;
  reach_count: number | null;
  comment_count: number | null;
  like_count: number | null;
  share_count: number | null;
  save_count: number | null;
  repost_count: number | null;
  total_engagement: number | null;
  url: string | null;
  data_recorded_at: string | null;
  external_id: string | null;
  is_manual: boolean;
  // 구분(카테고리) — 수동 태그(행사/기획/정책/이벤트/기타). null이면 미분류. (마이그레이션 035)
  category: PostCategory | null;
  created_at: string;
  // 댓글 AI 요약 캐시 (마이그레이션 034) — 저장된 요약을 즉시 표시하는 데 사용.
  comment_summary: string | null;
  comment_summary_at: string | null;
}

export interface MetricSnapshot {
  id: string;
  post_id: string;
  captured_at: string;
  period: string;
  views: number | null;
  reach: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  engagement_total: number | null;
  created_at: string;
}

export interface CreateContentRequest {
  posted_at: string;
  title?: string | null;
  content_type?: string | null;
  producer?: string | null;
  category?: PostCategory | null;
  url?: string | null;
  external_id?: string | null;
}

export interface CollectMetricsResponse {
  period: string;
  posts_processed: number;
  snapshots_added: number;
  snapshots_updated: number;
  skipped: number;
  posts_added: number;
  posts_updated: number;
  failures: string[];
}

export interface SnsComment {
  id: string;
  post_id: string;
  external_comment_id: string | null;
  author: string | null;
  text: string | null;
  translated_text: string | null;
  commented_at: string | null;
  like_count: number | null;
  created_at: string;
}

export interface CommentTranslateResponse {
  post_id: string;
  translated: number;
  comments: SnsComment[];
}

export interface CollectCommentsResponse {
  posts_processed: number;
  comments_added: number;
  comments_updated: number;
  skipped: number;
  failures: string[];
}

export interface SnsSnapshot {
  id: string;
  account_id: string;
  year: number;
  month: number;
  week_number: number;
  followers: number;
  captured_at: string;
  created_at: string;
}

export interface SnsImportResponse {
  accounts_added: number;
  snapshots_added: number;
  posts_added: number;
  posts_updated: number;
}

export interface SnsIngestResponse {
  posts_added: number;
  posts_updated: number;
  snapshots_added: number;
  snapshots_updated: number;
}

export interface CreateAccountRequest {
  platform: Platform;
  language: Language;
  handle?: string | null;
  page_url?: string | null;
  external_id?: string | null;
  is_active?: boolean;
  // 브랜드(광고주). 예: "서울시", "신세계". 채널 식별축.
  client?: string | null;
}

export interface UpdateAccountRequest {
  platform?: Platform;
  language?: Language;
  handle?: string | null;
  page_url?: string | null;
  external_id?: string | null;
  is_active?: boolean;
  client?: string | null;
}

export interface PostFilter {
  account_id?: string;
  date_from?: string;
  date_to?: string;
  content_type?: string;
  category?: PostCategory;
  producer?: string;
  language?: Language;
  platform?: Platform;
  keyword?: string;
  limit?: number;
  offset?: number;
}

export interface CreatePostRequest {
  account_id: string;
  posted_at: string;
  title?: string | null;
  content_type?: string | null;
  producer?: string | null;
  category?: PostCategory | null;
  view_count?: number | null;
  reach_count?: number | null;
  comment_count?: number | null;
  like_count?: number | null;
  share_count?: number | null;
  save_count?: number | null;
  repost_count?: number | null;
  url?: string | null;
}

export type UpdatePostRequest = Partial<CreatePostRequest>;

export interface SnapshotFilter {
  account_id?: string;
  year?: number;
  month?: number;
}

export interface UpsertSnapshotRequest {
  account_id: string;
  year: number;
  month: number;
  week_number: number;
  followers: number;
}

export const listAccounts = () => api.get<SnsAccount[]>("/api/sns/accounts");

export const createAccount = (data: CreateAccountRequest) =>
  api.post<SnsAccount>("/api/sns/accounts", data);

export const updateAccount = (id: string, data: UpdateAccountRequest) =>
  api.patch<SnsAccount>(`/api/sns/accounts/${id}`, data);

export interface DeleteAccountResponse {
  id: string;
  hard: boolean;
  deleted: boolean;
  posts_deleted: number;
  snapshots_deleted: number;
}

// 계정 삭제. hard=false(기본)는 소프트삭제(is_active=false), hard=true는 영구 삭제(하위 데이터 CASCADE).
export const deleteAccount = (id: string, hard = false) =>
  api.delete<DeleteAccountResponse>(`/api/sns/accounts/${id}`, { params: { hard } });

export const listPosts = (filter: PostFilter = {}) =>
  api.get<SnsPost[]>("/api/sns/posts", { params: filter });

// 제작주체(producer)별 게시물 수 집계 한 행. producer=null = 미지정.
export interface ProducerStat {
  producer: string | null;
  count: number;
}

export interface ProducerStatFilter {
  account_id?: string;
  date_from?: string;
  date_to?: string;
  language?: Language;
  platform?: Platform;
}

// 제작주체별 집계 — 서버 GROUP BY. 실제 존재하는 distinct producer 값을 동적 반환.
export const listProducerStats = (filter: ProducerStatFilter = {}) =>
  api.get<ProducerStat[]>("/api/sns/posts/producer-stats", { params: filter });

export const createPost = (data: CreatePostRequest) =>
  api.post<SnsPost>("/api/sns/posts", data);

export const updatePost = (id: string, data: UpdatePostRequest) =>
  api.patch<SnsPost>(`/api/sns/posts/${id}`, data);

export const listSnapshots = (filter: SnapshotFilter = {}) =>
  api.get<SnsSnapshot[]>("/api/sns/snapshots", { params: filter });

export const upsertSnapshot = (data: UpsertSnapshotRequest) =>
  api.post<SnsSnapshot>("/api/sns/snapshots", data);

export const bulkUpsertSnapshots = (data: UpsertSnapshotRequest[]) =>
  api.post<SnsSnapshot[]>("/api/sns/snapshots/bulk", data);

export interface TrendPoint {
  account_id: string;
  platform: Platform;
  language: Language;
  handle: string | null;
  year: number;
  month: number;
  week_number: number;
  period: string; // 예: "2026-05-W3"
  followers: number;
}

export interface TrendFilter {
  language?: Language;
  platform?: Platform;
  account_id?: string;
  months?: number;
}

// 채널별 팔로워 추이(시계열). 최근 months(기본 6)개월 범위.
export const listTrend = (filter: TrendFilter = {}) =>
  api.get<TrendPoint[]>("/api/sns/stats/trend", { params: filter });

// 콘텐츠 현황 — 계정(채널)별 주차별 게재건수 + 월 누적.
export interface WeeklyPostCountRow {
  account_id: string;
  platform: Platform;
  language: Language;
  handle: string | null;
  client: string | null;
  week1: number;
  week2: number;
  week3: number;
  week4: number;
  week5: number;
  total: number;
}

// 선택한 연/월의 계정별 주차별 게재건수 집계.
export const listWeeklyPostCounts = (params: { year: number; month: number }) =>
  api.get<WeeklyPostCountRow[]>("/api/sns/stats/weekly-posts", { params });

// ---------------- 엑셀 내보내기 (.xlsx blob 다운로드) ----------------

const XLSX_MIME =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

/** blob 응답을 받아 브라우저 다운로드를 트리거한다. fallbackName 은 헤더 부재 시 파일명. */
async function downloadXlsx(
  path: string,
  params: Record<string, unknown>,
  fallbackName: string,
): Promise<void> {
  const res = await api.get(path, { params, responseType: "blob" });
  const blob = new Blob([res.data], { type: XLSX_MIME });
  triggerBlobDownload(blob, fallbackName);
}

const pad2 = (n: number): string => String(n).padStart(2, "0");

/** 콘텐츠 현황(주차별 게재건수) — 선택한 연/월 .xlsx 다운로드. */
export const exportContentStatus = (params: { year: number; month: number }) =>
  downloadXlsx(
    "/api/sns/export/content-status",
    params,
    `콘텐츠현황_${params.year}-${pad2(params.month)}.xlsx`,
  );

/** 주간 팔로워 — 선택한 연/월 .xlsx 다운로드. */
export const exportSnapshots = (params: { year: number; month: number }) =>
  downloadXlsx(
    "/api/sns/export/snapshots",
    params,
    `주간팔로워_${params.year}-${pad2(params.month)}.xlsx`,
  );

/** 게시물 목록 — 계정/기간 .xlsx 다운로드. account_id 생략 시 기간 내 전체 계정. */
export const exportPosts = (params: {
  account_id?: string;
  date_from?: string;
  date_to?: string;
}) => {
  const period =
    params.date_from && params.date_to
      ? `${params.date_from}_${params.date_to}`
      : params.date_from
        ? `${params.date_from}_이후`
        : params.date_to
          ? `~${params.date_to}`
          : "전체";
  return downloadXlsx("/api/sns/export/posts", params, `게시물_${period}.xlsx`);
};

/**
 * 브랜드(client)별 통합 워크북 .xlsx 다운로드 — 월간요약 + 채널별 콘텐츠 + 팔로워.
 * 팀의 기존 구글시트 구조를 재현하며 marketing1 importer 와 라운드트립 호환된다.
 */
export const exportBrandWorkbook = (params: {
  client: string;
  year: number;
  month: number;
}) =>
  downloadXlsx(
    "/api/sns/export/workbook",
    params,
    `${params.client}_SNS_DB_${params.year}-${pad2(params.month)}.xlsx`,
  );

export const importMarketing1Excel = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<SnsImportResponse>("/api/sns/import/marketing1-excel", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const triggerCollect = (accountId: string, options: { full?: boolean } = {}) =>
  api.post<SnsIngestResponse>(`/api/sns/collect/${accountId}`, null, { params: options });

export interface RefreshAccountResult {
  account_id: string;
  platform: Platform;
  language: Language;
  handle: string | null;
  ok: boolean;
  posts_added: number;
  posts_updated: number;
  snapshots_added: number;
  snapshots_updated: number;
  metrics_processed: number;
  errors: string[];
}

export interface RefreshAllResponse {
  ok_count: number;
  failed_count: number;
  total: number;
  include_metrics: boolean;
  results: RefreshAccountResult[];
}

// 전체 갱신 — 모든 활성 계정의 게시물/팔로워(+옵션 메트릭)를 동기 일괄 수집(관리자).
// 계정별 실패는 격리되어 응답 results 에 담긴다. 갱신은 수 초~수십 초가 걸릴 수 있다.
export const refreshAll = (
  options: { includeMetrics?: boolean; period?: "daily" | "weekly" } = {},
) =>
  api.post<RefreshAllResponse>("/api/sns/refresh-all", null, {
    params: {
      include_metrics: options.includeMetrics ?? true,
      period: options.period ?? "daily",
    },
  });

export const resetAccountPosts = (accountId: string) =>
  api.delete<{ deleted: number }>(`/api/sns/accounts/${accountId}/posts`);

// 수동 콘텐츠 등록 (FALLBACK 모드) — 메타 토큰 없어도 동작.
export const createManualContent = (accountId: string, data: CreateContentRequest) =>
  api.post<SnsPost>(`/api/sns/accounts/${accountId}/contents`, data);

// 게시물 메트릭 일괄 수집 (메타 토큰 필요). period=daily|weekly.
export const collectMetrics = (accountId: string, period: "daily" | "weekly" = "daily") =>
  api.post<CollectMetricsResponse>(
    `/api/sns/accounts/${accountId}/collect-metrics`,
    null,
    { params: { period } },
  );

// 게시물 메트릭 시계열 조회 (오래된→최신).
export const listPostMetrics = (postId: string, period?: "daily" | "weekly") =>
  api.get<MetricSnapshot[]>(`/api/sns/posts/${postId}/metrics`, {
    params: period ? { period } : undefined,
  });

// 게시물 댓글 본문 일괄 수집 (메타 토큰 필요, 소유/관리 계정 한정).
export const collectComments = (accountId: string) =>
  api.post<CollectCommentsResponse>(
    `/api/sns/accounts/${accountId}/collect-comments`,
    null,
  );

// 게시물 댓글 목록 조회 (오래된→최신).
export const listPostComments = (postId: string, params: { limit?: number; offset?: number } = {}) =>
  api.get<SnsComment[]>(`/api/sns/posts/${postId}/comments`, { params });

export interface CommentAnalysis {
  post_id: string;
  comment_count: number;
  summary: string;
  summary_at: string | null;
}

// 게시물 댓글 AI 분석/요약 (한국어). 먼저 댓글 수집 필요 + ANTHROPIC_API_KEY.
// force=true면 캐시된 요약이 있어도 다시 분석한다(명시적 재요약).
export const analyzePostComments = (postId: string, force = false) =>
  api.post<CommentAnalysis>(
    `/api/sns/posts/${postId}/comments/analyze`,
    null,
    { params: { force } },
  );

// 게시물 댓글 다국어→한국어 번역. 원문 보존, 번역문만 캐시. force=true면 재번역.
export const translatePostComments = (postId: string, force = false) =>
  api.post<CommentTranslateResponse>(
    `/api/sns/posts/${postId}/comments/translate`,
    null,
    { params: { force } },
  );

export const PLATFORM_LABELS: Record<Platform, string> = {
  facebook: "페이스북",
  instagram: "인스타그램",
  twitter: "트위터",
  youtube: "유튜브",
  weibo: "웨이보",
};

export const LANGUAGE_LABELS: Record<Language, string> = {
  en: "영문",
  zh: "중간체",
  ja: "일문",
};

export const CONTENT_TYPE_LABELS: Record<string, string> = {
  image: "이미지",
  video: "영상",
  short: "숏폼",
  post: "게시물",
  reel: "릴스",
};

// 구분(카테고리) — 수동 태그. SNS API 로는 못 긁어오는 분류 축. 단일 출처(여기서만 정의).
export const POST_CATEGORIES: readonly PostCategory[] = [
  "행사",
  "기획",
  "정책",
  "이벤트",
  "기타",
] as const;

// 구분별 태그 색상 (UI 일관성). 미분류(null)는 별도 처리.
export const POST_CATEGORY_COLORS: Record<PostCategory, string> = {
  행사: "magenta",
  기획: "blue",
  정책: "green",
  이벤트: "volcano",
  기타: "default",
};

export const POST_CATEGORY_OPTIONS = POST_CATEGORIES.map((value) => ({
  value,
  label: value,
}));

// 제작주체(producer) — 형태(content_type)와 별도. 서울시 SNS 시트 '제작' 열 기준.
// producer 는 자유 입력 텍스트라 DB 에는 이 외의 값(예: "자체제작")도 존재할 수 있다.
// 아래는 수동 등록 폼·필터의 표준 선택지(canonical)일 뿐, 집계는 서버 GROUP BY 로 동적 처리한다.
export const PRODUCER_VALUES = ["서울시제공", "TK제작", "인플루언서"] as const;

export const PRODUCER_OPTIONS = PRODUCER_VALUES.map((value) => ({
  value,
  label: value,
}));

export const PLATFORM_OPTIONS = (Object.keys(PLATFORM_LABELS) as Platform[]).map((value) => ({
  value,
  label: PLATFORM_LABELS[value],
}));

export const LANGUAGE_OPTIONS = (Object.keys(LANGUAGE_LABELS) as Language[]).map((value) => ({
  value,
  label: LANGUAGE_LABELS[value],
}));

export const CONTENT_TYPE_OPTIONS = Object.keys(CONTENT_TYPE_LABELS).map((value) => ({
  value,
  label: CONTENT_TYPE_LABELS[value],
}));

export function getPlatformLabel(value: string | null | undefined): string {
  if (!value) return "-";
  return PLATFORM_LABELS[value as Platform] ?? value;
}

export function getLanguageLabel(value: string | null | undefined): string {
  if (!value) return "-";
  return LANGUAGE_LABELS[value as Language] ?? value;
}

export function getContentTypeLabel(value: string | null | undefined): string {
  if (!value) return "-";
  return CONTENT_TYPE_LABELS[value] ?? value;
}
