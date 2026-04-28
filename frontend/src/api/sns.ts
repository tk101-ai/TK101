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
  created_at: string;
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

export const importMarketing1Excel = (file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post<SnsImportResponse>("/api/sns/import/marketing1-excel", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
};

export const triggerCollect = (accountId: string) =>
  api.post<SnsIngestResponse>(`/api/sns/collect/${accountId}`);

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
};

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
