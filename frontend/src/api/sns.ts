import api from "./client";

export type Platform = "facebook" | "instagram" | "twitter" | "youtube" | "weibo";
export type Language = "en" | "zh" | "ja";

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
  created_at: string;
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
}

export interface UpdateAccountRequest {
  platform?: Platform;
  language?: Language;
  handle?: string | null;
  page_url?: string | null;
  external_id?: string | null;
  is_active?: boolean;
}

export interface PostFilter {
  account_id?: string;
  date_from?: string;
  date_to?: string;
  content_type?: string;
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

export const importMarketing1Excel = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<SnsImportResponse>("/api/sns/import/marketing1-excel", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const triggerCollect = (accountId: string, options: { full?: boolean } = {}) =>
  api.post<SnsIngestResponse>(`/api/sns/collect/${accountId}`, null, { params: options });

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
}

// 게시물 댓글 AI 분석/요약 (한국어). 먼저 댓글 수집 필요 + ANTHROPIC_API_KEY.
export const analyzePostComments = (postId: string) =>
  api.post<CommentAnalysis>(`/api/sns/posts/${postId}/comments/analyze`);

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

// 제작주체 (형태와 별도). 서울시 SNS 시트 기준 값.
export const PRODUCER_LABELS: Record<string, string> = {
  서울제작: "서울제작",
  TK제작: "TK제작",
  플랫폼언서제작: "플랫폼언서제작",
};

export const PRODUCER_OPTIONS = Object.keys(PRODUCER_LABELS).map((value) => ({
  value,
  label: PRODUCER_LABELS[value],
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
