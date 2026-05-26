import api from "./client";

/**
 * 신사업유통 모듈 — 텔레그램 페르소나 API 클라이언트 (T9 Phase A).
 *
 * 백엔드: `app/routers/distribution.py`
 *
 * 페르소나는 텔레그램 다계정 운영을 위한 단위. 어드민이 라벨/역할/표시명/폰
 * 번호와 my.telegram.org 발급 api_id/api_hash 를 등록한 뒤 SMS 2단계 인증으로
 * Telethon 세션을 로그인한다. 세션 파일은 백엔드에서 Fernet 으로 암호화 저장.
 */

export type PersonaRole = "vietnam_admin" | "domestic_admin";

export interface PersonaOut {
  id: string;
  account_label: string;
  role: PersonaRole;
  display_name: string;
  business_name: string | null;
  telegram_phone: string;
  telegram_user_id: number | null;
  has_credentials: boolean;
  is_logged_in: boolean;
  tone_profile: Record<string, unknown> | null;
  daily_msg_limit: number;
  active: boolean;
  warmup_until: string | null;
  last_login_at: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface PersonaUpdatePayload {
  display_name?: string;
  business_name?: string | null;
  active?: boolean;
}

export interface PersonaCreatePayload {
  account_label: string;
  role: PersonaRole;
  display_name: string;
  telegram_phone: string;
  api_id: string;
  api_hash: string;
  tone_profile?: Record<string, unknown> | null;
  daily_msg_limit?: number;
  warmup_days?: number;
}

export interface LoginInitResponse {
  phone_code_hash: string;
  sent_to_phone_masked: string;
}

export interface VerifyCodePayload {
  phone_code_hash: string;
  code: string;
  password?: string | null;
}

export interface VerifyCodeResponse {
  telegram_user_id: number;
  display_name: string;
  username: string | null;
}

const BASE = "/api/distribution";

/** 백엔드 응답 envelope — `{ personas: PersonaOut[] }`. */
interface ListPersonasResponse {
  personas: PersonaOut[];
}

export async function listPersonas(): Promise<PersonaOut[]> {
  const res = await api.get<ListPersonasResponse>(`${BASE}/personas`);
  return res.data.personas;
}

export async function createPersona(
  payload: PersonaCreatePayload,
): Promise<PersonaOut> {
  const res = await api.post<PersonaOut>(`${BASE}/personas`, payload);
  return res.data;
}

export async function deletePersona(id: string): Promise<void> {
  await api.delete(`${BASE}/personas/${id}`);
}

export interface PersonaCredentialsPayload {
  telegram_phone: string;
  api_id: string;
  api_hash: string;
}

/**
 * placeholder seed 페르소나 채우기 또는 기존 api_id/hash 회전.
 * 기존 Telethon 세션은 백엔드에서 자동 무효화됨 → 재로그인 필요.
 */
export async function updatePersonaCredentials(
  id: string,
  payload: PersonaCredentialsPayload,
): Promise<PersonaOut> {
  const res = await api.put<PersonaOut>(
    `${BASE}/personas/${id}/credentials`,
    payload,
  );
  return res.data;
}

export async function logoutPersona(id: string): Promise<PersonaOut> {
  const res = await api.post<PersonaOut>(`${BASE}/personas/${id}/logout`);
  return res.data;
}

export async function initLogin(id: string): Promise<LoginInitResponse> {
  const res = await api.post<LoginInitResponse>(
    `${BASE}/personas/${id}/login-init`,
  );
  return res.data;
}

export async function verifyCode(
  id: string,
  payload: VerifyCodePayload,
): Promise<VerifyCodeResponse> {
  const res = await api.post<VerifyCodeResponse>(
    `${BASE}/personas/${id}/verify-code`,
    payload,
  );
  return res.data;
}

export const PERSONA_ROLE_LABEL: Record<PersonaRole, string> = {
  vietnam_admin: "베트남 어드민",
  domestic_admin: "국내 어드민",
};

export const PERSONA_ROLE_TAG_COLOR: Record<PersonaRole, string> = {
  vietnam_admin: "blue",
  domestic_admin: "green",
};

export const PERSONA_ROLE_OPTIONS: { value: PersonaRole; label: string }[] = [
  { value: "vietnam_admin", label: "베트남 어드민" },
  { value: "domestic_admin", label: "국내 어드민" },
];

// ---------------------------------------------------------------------------
// Phase B-1: Weekly Summary + Products
// ---------------------------------------------------------------------------

export interface WeeklySummaryOut {
  id: string;
  company_label: string;
  period_label: string;
  period_start: string; // ISO date
  period_end: string;
  kr_purchase: string | null; // Decimal as string
  vn_inventory_move: string | null;
  vn_sales_completed: string | null;
  kr_purchase_deposit_req: string | null;
  vn_inventory_deposit_req: string | null;
  vn_sales_deposit_req: string | null;
  account_deposit: string | null;
  cash_deposit: string | null;
  source_file: string | null;
  imported_at: string;
}

export interface ProductOut {
  id: string;
  brand: string;
  product_name_en: string | null;
  product_code: string | null;
  category: string | null;
  purchase_qty: number | null;
  domestic_stock_qty: number | null;
  // VN(베트남) 수량 — 명품재고대장 컬럼 19/21/22.
  vn_inventory_move_qty: number | null;
  vn_sales_completed_qty: number | null;
  vn_local_stock_qty: number | null;
  supply_price: string | null;
  purchase_price: string | null;
  approval_number: string | null;
  purchase_date: string | null;
  source_file: string | null;
  imported_at: string;
  company_label?: string | null;
}

export interface DataUploadResult {
  file_name: string;
  summary_inserted: number;
  summary_updated: number;
  products_inserted: number;
  products_wiped: number;
  warnings: string[];
  company_label?: string | null;
}

// ---------------------------------------------------------------------------
// T9 Phase F-D: 4 회사 통합 운영 (TK101 / 래더엑스 / 뉴테인핏 / SYBT)
// ---------------------------------------------------------------------------

/** 신사업유통이 운영 중인 4 회사 코드. backend constants 와 동기화 필수. */
export const DISTRIBUTION_COMPANIES = [
  "TK101",
  "래더엑스",
  "뉴테인핏",
  "SYBT",
] as const;
export type DistributionCompany = (typeof DISTRIBUTION_COMPANIES)[number];

/** 페이지 상단 회사 Select 표준 옵션 — "전체" 포함. */
export const COMPANY_FILTER_OPTIONS: {
  value: DistributionCompany | "all";
  label: string;
}[] = [
  { value: "all", label: "전체 (4 회사 합산)" },
  { value: "TK101", label: "TK101" },
  { value: "래더엑스", label: "래더엑스" },
  { value: "뉴테인핏", label: "뉴테인핏" },
  { value: "SYBT", label: "SYBT" },
];

/** 업로드 폼 등 "전체" 가 무의미한 곳에서 쓰는 옵션 — 4 회사만. */
export const COMPANY_SELECT_OPTIONS: {
  value: DistributionCompany;
  label: string;
}[] = DISTRIBUTION_COMPANIES.map((c) => ({ value: c, label: c }));

/** 데이터에 등록된 회사 목록 — Agent A 의 /data/companies 가 있으면 사용. */
export async function listDistributionCompanies(): Promise<string[]> {
  const res = await api.get<{ items: string[] }>(`${BASE}/data/companies`);
  return res.data.items;
}

export async function uploadDistributionData(
  file: File,
  companyLabel?: string,
): Promise<DataUploadResult> {
  const formData = new FormData();
  formData.append("file", file);
  if (companyLabel) formData.append("company_label", companyLabel);
  const res = await api.post<DataUploadResult>(
    `${BASE}/data/upload`,
    formData,
    {
      headers: { "Content-Type": "multipart/form-data" },
    },
  );
  return res.data;
}

export interface WeeklySummaryFilter {
  limit?: number;
  from?: string; // YYYY-MM-DD
  to?: string;
  company_label?: string;
}

export async function listWeeklySummary(
  filter: WeeklySummaryFilter = {},
): Promise<WeeklySummaryOut[]> {
  const params: Record<string, string | number> = {
    limit: filter.limit ?? 200,
  };
  if (filter.from) params.from = filter.from;
  if (filter.to) params.to = filter.to;
  if (filter.company_label) params.company_label = filter.company_label;
  const res = await api.get<{ items: WeeklySummaryOut[] }>(
    `${BASE}/data/weekly-summary`,
    { params },
  );
  return res.data.items;
}

export interface ProductsFilter {
  limit?: number;
  company_label?: string;
  brand?: string;
  category?: string;
  search?: string;
}

export async function listProducts(
  filter: ProductsFilter | number = {},
): Promise<ProductOut[]> {
  // 하위호환: 과거 시그니처 listProducts(limit: number) 도 허용.
  const normalized: ProductsFilter =
    typeof filter === "number" ? { limit: filter } : filter;
  const params: Record<string, string | number> = {
    limit: normalized.limit ?? 1000,
  };
  if (normalized.company_label) params.company_label = normalized.company_label;
  if (normalized.brand) params.brand = normalized.brand;
  if (normalized.category) params.category = normalized.category;
  if (normalized.search) params.search = normalized.search;
  const res = await api.get<{ items: ProductOut[] }>(`${BASE}/data/products`, {
    params,
  });
  return res.data.items;
}

// ---------------------------------------------------------------------------
// Phase A 보강: 페르소나 일반 PATCH (사업자명/표시명/active)
// ---------------------------------------------------------------------------

/**
 * 페르소나 필드 부분 갱신.
 *
 * - `business_name`/`display_name`/`active` 만 갱신. 자격증명·세션 미관여.
 * - 자격증명 회전은 `updatePersonaCredentials` 별도 엔드포인트 사용.
 */
export async function updatePersona(
  id: string,
  payload: PersonaUpdatePayload,
): Promise<PersonaOut> {
  const res = await api.patch<PersonaOut>(`${BASE}/personas/${id}`, payload);
  return res.data;
}

// ---------------------------------------------------------------------------
// Phase C: 세션 검수 / 메시지 편집 / 송신
// ---------------------------------------------------------------------------

export type SessionStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "sending"
  | "sent"
  | "failed";

export type MessageStatus = "queued" | "sent" | "failed" | "skipped";

export interface SessionListItem {
  id: string;
  scenario_name: string;
  sender_account_label: string;
  receiver_account_label: string;
  status: SessionStatus;
  generated_at: string;
  approved_at: string | null;
  completed_at: string | null;
  scheduled_start: string | null;
  message_count: number;
  llm_cost_usd: string | null;
  /** 시나리오가 첨부 권장이면 true (T9 — 2026-05-26). */
  scenario_attachment_required: boolean;
}

export type AttachmentKind = "image" | "document";

export interface MessageItem {
  id: string;
  order_index: number;
  sender_account_label: string;
  content: string;
  edited_content: string | null;
  user_edited: boolean;
  send_after_sec: number;
  typing_sec: number;
  status: MessageStatus;
  sent_at: string | null;
  telegram_message_id: string | null;
  /** 첨부 파일 (T9 — 2026-05-26). attachment_url 이 있으면 첨부 있음. */
  attachment_filename: string | null;
  attachment_mime: string | null;
  attachment_kind: AttachmentKind | null;
  attachment_caption: string | null;
  attachment_url: string | null;
}

export interface SessionDetail {
  session: SessionListItem;
  messages: MessageItem[];
}

export interface SendNowResult {
  session_id: string;
  status: SessionStatus;
  sent_count: number;
  failed_count: number;
  error: string | null;
}

export interface ListSessionsParams {
  status?: SessionStatus;
  limit?: number;
  offset?: number;
}

export interface ListSessionsResponse {
  items: SessionListItem[];
  total?: number;
}

/** 세션 목록. status 필터·페이지네이션 지원. */
export async function listSessions(
  params: ListSessionsParams = {},
): Promise<ListSessionsResponse> {
  const res = await api.get<ListSessionsResponse>(`${BASE}/sessions`, {
    params: {
      status: params.status,
      limit: params.limit ?? 50,
      offset: params.offset ?? 0,
    },
  });
  return res.data;
}

/** 세션 상세 (헤더 + 메시지 리스트). */
export async function getSession(id: string): Promise<SessionDetail> {
  const res = await api.get<SessionDetail>(`${BASE}/sessions/${id}`);
  return res.data;
}

/**
 * 세션 승인.
 *
 * `scheduled_start` 가 null/미지정이면 즉시 송신 가능 상태로 전환.
 * 값이 있으면 워커가 해당 시각 이후에 픽업.
 */
export async function approveSession(
  id: string,
  scheduledStart?: string | null,
): Promise<SessionListItem> {
  const res = await api.post<SessionListItem>(
    `${BASE}/sessions/${id}/approve`,
    { scheduled_start: scheduledStart ?? null },
  );
  return res.data;
}

/** 세션 거부. `reason` 은 운영자 메모용. */
export async function rejectSession(
  id: string,
  reason?: string,
): Promise<SessionListItem> {
  const res = await api.post<SessionListItem>(`${BASE}/sessions/${id}/reject`, {
    reason: reason ?? null,
  });
  return res.data;
}

/** 즉시 송신 (동기). 응답은 송신 결과 요약. */
export async function sendSessionNow(id: string): Promise<SendNowResult> {
  const res = await api.post<SendNowResult>(`${BASE}/sessions/${id}/send-now`);
  return res.data;
}

/** 메시지 1개 본문 편집. 비어있는 본문은 백엔드에서 422 로 거부. */
export async function updateMessage(
  id: string,
  editedContent: string,
): Promise<MessageItem> {
  const res = await api.patch<MessageItem>(`${BASE}/messages/${id}`, {
    edited_content: editedContent,
  });
  return res.data;
}

/** 메시지 송신 텀(send_after_sec) 만 갱신. 본문은 그대로 둠. */
export async function updateMessageTiming(
  id: string,
  sendAfterSec: number,
): Promise<MessageItem> {
  const res = await api.patch<MessageItem>(`${BASE}/messages/${id}`, {
    send_after_sec: sendAfterSec,
  });
  return res.data;
}

/**
 * 메시지에 파일 첨부 (T9 — 2026-05-26).
 *
 * - 이미지 (JPG/PNG/WebP/GIF) 또는 문서 (PDF/엑셀/한글 등) 1건.
 * - 최대 20MB. 허용되지 않는 확장자/크기는 백엔드에서 415/413.
 * - 이미 송신된 메시지는 422.
 * - 동일 메시지에 재업로드 시 기존 파일 덮어쓰기.
 */
export async function uploadMessageAttachment(
  id: string,
  file: File,
  caption?: string | null,
): Promise<MessageItem> {
  const form = new FormData();
  form.append("file", file);
  const url = caption
    ? `${BASE}/messages/${id}/attachment?caption=${encodeURIComponent(caption)}`
    : `${BASE}/messages/${id}/attachment`;
  const res = await api.post<MessageItem>(url, form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return res.data;
}

/** 첨부 제거. 이미 송신된 메시지는 422. */
export async function deleteMessageAttachment(
  id: string,
): Promise<MessageItem> {
  const res = await api.delete<MessageItem>(`${BASE}/messages/${id}/attachment`);
  return res.data;
}

export const SESSION_STATUS_LABEL: Record<SessionStatus, string> = {
  pending: "검수 대기",
  approved: "승인됨",
  rejected: "거부됨",
  sending: "송신 중",
  sent: "송신 완료",
  failed: "실패",
};

export const SESSION_STATUS_TAG_COLOR: Record<SessionStatus, string> = {
  pending: "gold",
  approved: "blue",
  rejected: "default",
  sending: "processing",
  sent: "green",
  failed: "red",
};

export const MESSAGE_STATUS_LABEL: Record<MessageStatus, string> = {
  queued: "대기",
  sent: "송신됨",
  failed: "실패",
  skipped: "건너뜀",
};

export const MESSAGE_STATUS_TAG_COLOR: Record<MessageStatus, string> = {
  queued: "default",
  sent: "green",
  failed: "red",
  skipped: "gold",
};

// ---------------------------------------------------------------------------
// Phase B-2: 주간 생성 트리거
// ---------------------------------------------------------------------------

export interface GenerateWeeklyPayload {
  scenario_names?: string[];
  company_label?: string;
}

export interface GenerateWeeklyResult {
  sessions_created: string[];
  skipped: string[];
  errors: string[];
}

export async function generateWeekly(
  payload: GenerateWeeklyPayload = {},
): Promise<GenerateWeeklyResult> {
  const res = await api.post<GenerateWeeklyResult>(`${BASE}/generate-weekly`, {
    scenario_names: payload.scenario_names ?? [],
    company_label: payload.company_label ?? "래더엑스",
  });
  return res.data;
}
