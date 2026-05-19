import api from "./client";

/**
 * AI Playground API 클라이언트 (T8 Phase 1 — admin 전용).
 *
 * 백엔드: `app/routers/playground.py` (Phase 1에서 추가 예정).
 * 스트리밍 채팅은 SSE(Server-Sent Events)로 수신한다.
 *
 * 모듈: `playground` (admin only, system 카테고리).
 */

/** Phase 3 에서 grok/kimi/glm/minimax/deepseek 추가 예정 — 일반 string 으로 완화. */
export type PlaygroundProviderKey = string;

export interface PlaygroundModelVariant {
  /** 정확한 모델 ID. 예: "claude-haiku-4-5-20251001" */
  id: string;
  /** UI 라벨. 예: "Haiku 4.5" */
  label: string;
  /** Optional 부가 뱃지 텍스트(예: "NEW"). */
  badge?: string | null;
}

export interface PlaygroundProvider {
  key: PlaygroundProviderKey;
  /** UI 카드명. 예: "Claude" */
  name: string;
  /** 변형 개수 뱃지 — 카드 우상단. 예: "3v" */
  versionBadge: string;
  /** Phase 1: claude만 enabled, 나머지는 미구현 placeholder. */
  enabled: boolean;
  /** chip 변형 리스트. */
  variants: PlaygroundModelVariant[];
}

export interface PlaygroundSession {
  id: string;
  user_id: string;
  title: string | null;
  provider: string;
  model: string;
  system_prompt: string | null;
  temperature: number;
  created_at: string;
  updated_at: string;
}

export interface PlaygroundMessage {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  input_tokens: number | null;
  output_tokens: number | null;
  reasoning_tokens: number | null;
  cached_tokens: number | null;
  total_tokens: number | null;
  latency_ms: number | null;
  model: string | null;
  created_at: string;
}

export interface CreateSessionBody {
  provider: PlaygroundProviderKey;
  model: string;
  system_prompt?: string | null;
  temperature?: number;
  title?: string | null;
}

/**
 * SSE chunk 타입 (백엔드 합의).
 * - text_delta: 토큰 스트림
 * - usage: 최종 사용량 (input/output/reasoning/cached/total/latency_ms)
 * - done: 스트림 종료
 * - error: 에러 (message 포함)
 */
export type PlaygroundChunk =
  | { type: "text_delta"; content: string }
  | {
      type: "usage";
      input?: number;
      output?: number;
      reasoning?: number;
      cached?: number;
      total?: number;
      latency_ms?: number;
      model?: string;
    }
  | { type: "done"; message_id?: string }
  | { type: "error"; message: string };

const BASE = "/api/playground";

/**
 * 백엔드 SSE chunk 의 raw shape (`text_delta`는 `delta`, `usage`는 `input_tokens` 등)을
 * 프론트엔드 hook이 기대하는 normalized shape (`content`, `input/output/...`) 로 변환.
 *
 * Phase 1 작성 시점부터 양쪽 키 이름이 어긋나 있어 "undefined" 가 누적되던 문제 보정.
 */
function normalizeChunk(raw: Record<string, unknown>): PlaygroundChunk {
  const t = raw.type;
  if (t === "text_delta") {
    const delta =
      (typeof raw.delta === "string" && raw.delta) ||
      (typeof raw.content === "string" && raw.content) ||
      "";
    return { type: "text_delta", content: delta };
  }
  if (t === "usage") {
    const num = (k: string): number | undefined => {
      const v = raw[k];
      return typeof v === "number" ? v : undefined;
    };
    const cacheRead = num("cache_read_input_tokens") ?? 0;
    const cacheCreate = num("cache_creation_input_tokens") ?? 0;
    const cachedTotal =
      cacheRead + cacheCreate > 0 ? cacheRead + cacheCreate : num("cached");
    const input = num("input_tokens") ?? num("input");
    const output = num("output_tokens") ?? num("output");
    return {
      type: "usage",
      input,
      output,
      reasoning: num("reasoning_tokens") ?? num("reasoning"),
      cached: cachedTotal,
      total:
        num("total_tokens") ??
        num("total") ??
        (input !== undefined && output !== undefined ? input + output : undefined),
      latency_ms: num("latency_ms"),
      model: typeof raw.model === "string" ? raw.model : undefined,
    };
  }
  if (t === "done") {
    return {
      type: "done",
      message_id: typeof raw.message_id === "string" ? raw.message_id : undefined,
    };
  }
  if (t === "error") {
    return {
      type: "error",
      message: typeof raw.message === "string" ? raw.message : "스트림 오류",
    };
  }
  return raw as unknown as PlaygroundChunk;
}

/** 백엔드 `/api/playground/providers` 응답 (PlaygroundProviderMeta). */
interface BackendProvider {
  provider_key: string;
  provider_label: string;
  models: Array<{ key: string; label: string; badge?: string | null }>;
}

export async function getProviders(): Promise<PlaygroundProvider[]> {
  const res = await api.get<BackendProvider[]>(`${BASE}/providers`);
  // 백엔드 shape → 프론트 shape 어댑터.
  return res.data.map((p) => ({
    key: p.provider_key,
    name: p.provider_label,
    versionBadge: `${p.models.length}v`,
    enabled: p.models.length > 0,
    variants: p.models.map((m) => ({
      id: m.key,
      label: m.label,
      badge: m.badge ?? null,
    })),
  }));
}

export async function createSession(body: CreateSessionBody): Promise<PlaygroundSession> {
  const res = await api.post<PlaygroundSession>(`${BASE}/sessions`, body);
  return res.data;
}

export async function listSessions(q?: string): Promise<PlaygroundSession[]> {
  const params: Record<string, string> = {};
  if (q && q.trim()) params.q = q.trim();
  const res = await api.get<PlaygroundSession[]>(`${BASE}/sessions`, { params });
  return res.data;
}

/** 검색어 q 기반 세션 검색 (listSessions 의 명시적 별칭). */
export async function searchSessions(
  q: string,
  limit = 50,
): Promise<PlaygroundSession[]> {
  const params: Record<string, string | number> = { limit };
  if (q && q.trim()) params.q = q.trim();
  const res = await api.get<PlaygroundSession[]>(`${BASE}/sessions`, { params });
  return res.data;
}

export async function deleteSession(id: string): Promise<void> {
  await api.delete(`${BASE}/sessions/${id}`);
}

export interface PatchSessionBody {
  title: string;
}

export async function patchSession(
  id: string,
  body: PatchSessionBody,
): Promise<PlaygroundSession> {
  const res = await api.patch<PlaygroundSession>(`${BASE}/sessions/${id}`, body);
  return res.data;
}

/**
 * 세션 export — 백엔드가 text/markdown (또는 다른 format) 으로 반환.
 * 호출자는 응답 text 를 Blob 으로 변환하여 다운로드한다.
 */
export async function exportSession(
  id: string,
  format: "md" | "json" = "md",
): Promise<string> {
  const res = await api.get<string>(`${BASE}/sessions/${id}/export`, {
    params: { format },
    responseType: "text",
    // axios 가 text/markdown 을 JSON 으로 파싱하지 않도록.
    transformResponse: [(data: unknown) => (typeof data === "string" ? data : String(data ?? ""))],
  });
  return res.data;
}

export async function getSessionMessages(id: string): Promise<PlaygroundMessage[]> {
  const res = await api.get<PlaygroundMessage[]>(`${BASE}/sessions/${id}/messages`);
  return res.data;
}

export interface StreamChatBody {
  session_id: string;
  /** 백엔드 `PlaygroundChatRequest.message` 필드와 매칭. */
  message: string;
  provider: PlaygroundProviderKey;
  model: string;
  system_prompt?: string | null;
  temperature?: number;
}

export interface StreamChatHandlers {
  onChunk: (chunk: PlaygroundChunk) => void;
  onError?: (err: Error) => void;
  onClose?: () => void;
  signal?: AbortSignal;
}

/**
 * /api/playground/chat 으로 사용자 메시지를 POST하고 SSE 스트림을 소비한다.
 *
 * EventSource는 GET 전용이라 POST + ReadableStream 패턴 사용.
 * fetch + getReader로 라인 단위 파싱한다 (`data: {json}\n\n`).
 *
 * 호출자는 `onChunk`에서 chunk 타입별 분기로 메시지/메트릭을 누적한다.
 */
export async function streamChat(
  body: StreamChatBody,
  handlers: StreamChatHandlers,
): Promise<void> {
  const token = localStorage.getItem("token");
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(`${BASE}/chat`, {
      method: "POST",
      headers,
      credentials: "include",
      body: JSON.stringify(body),
      signal: handlers.signal,
    });
  } catch (err: unknown) {
    handlers.onError?.(err instanceof Error ? err : new Error("network error"));
    return;
  }

  if (!response.ok || !response.body) {
    // 한도 초과 (402) 는 명시적 메시지로 변환 — 호출자가 isQuotaExceededError 로 분기 가능.
    if (response.status === 402) {
      const err = new Error(QUOTA_EXCEEDED_MESSAGE) as Error & {
        status?: number;
        response?: { status: number };
      };
      err.status = 402;
      err.response = { status: 402 };
      handlers.onError?.(err);
      return;
    }
    handlers.onError?.(new Error(`Playground SSE 응답 실패 (${response.status})`));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      // SSE 이벤트는 `\n\n`로 구분된다.
      let sep = buffer.indexOf("\n\n");
      while (sep !== -1) {
        const rawEvent = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        sep = buffer.indexOf("\n\n");

        const dataLines: string[] = [];
        for (const line of rawEvent.split("\n")) {
          if (line.startsWith("data:")) {
            dataLines.push(line.slice(5).trimStart());
          }
        }
        if (dataLines.length === 0) continue;
        const dataStr = dataLines.join("\n");
        if (dataStr === "[DONE]") {
          handlers.onChunk({ type: "done" });
          continue;
        }
        try {
          const raw = JSON.parse(dataStr) as Record<string, unknown>;
          handlers.onChunk(normalizeChunk(raw));
        } catch {
          // 잘못된 JSON은 무시 (heartbeat 등).
        }
      }
    }
  } catch (err: unknown) {
    if ((err as Error)?.name === "AbortError") {
      handlers.onClose?.();
      return;
    }
    handlers.onError?.(err instanceof Error ? err : new Error("stream error"));
    return;
  }

  handlers.onClose?.();
}

// ---------------------------------------------------------------------------
// Image / Video — Phase 4/5 뼈대
// ---------------------------------------------------------------------------

export interface PlaygroundMediaModelOption {
  key: string;
  label: string;
  badge: string | null;
}

export interface PlaygroundMediaCatalog {
  image: PlaygroundMediaModelOption[];
  video: PlaygroundMediaModelOption[];
}

export interface PlaygroundTaskCreated {
  task_id: string;
  request_id: string | null;
  kind: "image" | "video";
}

export type PlaygroundTaskStatusValue =
  | "pending"
  | "running"
  | "succeeded"
  | "failed"
  | "unknown";

export interface PlaygroundTaskStatus {
  task_id: string;
  kind: "image" | "video";
  status: PlaygroundTaskStatusValue;
  output_url: string | null;
  error_message: string | null;
  raw: Record<string, unknown> | null;
}

export interface CreateImageBody {
  prompt: string;
  model_key?: string;
  negative_prompt?: string | null;
  aspect_ratio?: string;
  enhance_prompt?: boolean;
}

export interface CreateVideoBody {
  prompt: string;
  model_key?: string;
  duration?: number;
  resolution?: string;
  aspect_ratio?: string;
  audio_generation?: boolean;
  enhance_prompt?: boolean;
}

export async function getMediaModels(): Promise<PlaygroundMediaCatalog> {
  const res = await api.get<PlaygroundMediaCatalog>(`${BASE}/media-models`);
  return res.data;
}

export async function createImageTask(
  body: CreateImageBody,
): Promise<PlaygroundTaskCreated> {
  const res = await api.post<PlaygroundTaskCreated>(`${BASE}/image`, body);
  return res.data;
}

export async function createVideoTask(
  body: CreateVideoBody,
): Promise<PlaygroundTaskCreated> {
  const res = await api.post<PlaygroundTaskCreated>(`${BASE}/video`, body);
  return res.data;
}

export interface CreateVideoFromMediaBody {
  prompt: string;
  image_media_id: string; // UUID of existing image media row
  model_key: string;
  duration: number;
  resolution: string;
  aspect_ratio: string;
  audio_generation: boolean;
  enhance_prompt: boolean;
}

/**
 * 기존 이미지 미디어(image_media_id)를 기반으로 영상 task 를 생성.
 * 백엔드 endpoint: POST /api/playground/video/from-media
 */
export async function createVideoFromMedia(
  body: CreateVideoFromMediaBody,
): Promise<PlaygroundTaskCreated> {
  const res = await api.post<PlaygroundTaskCreated>(
    `${BASE}/video/from-media`,
    body,
  );
  return res.data;
}

export async function describeTask(
  kind: "image" | "video",
  taskId: string,
): Promise<PlaygroundTaskStatus> {
  const res = await api.get<PlaygroundTaskStatus>(
    `${BASE}/tasks/${kind}/${encodeURIComponent(taskId)}`,
  );
  return res.data;
}

// ---------------------------------------------------------------------------
// 미디어 영속화 (갤러리) + 사용량 (admin only)
// ---------------------------------------------------------------------------

export interface PlaygroundMediaItem {
  id: string;
  media_type: "image" | "video";
  task_id: string | null;
  model_key: string | null;
  prompt: string | null;
  status: "pending" | "running" | "succeeded" | "failed" | "unknown";
  error_message: string | null;
  url: string | null;          // 텐센트 임시 URL (7일 만료)
  file_path: string | null;    // 백엔드 디스크 절대 경로 (직접 노출 X)
  duration_sec: number | null;
  width: number | null;
  height: number | null;
  cost_usd: number | null;
  expires_at: string | null;
  created_at: string;
}

export async function getMyMedia(
  kind?: "image" | "video",
  limit = 50,
): Promise<PlaygroundMediaItem[]> {
  const params: Record<string, string | number> = { limit };
  if (kind) params.kind = kind;
  const res = await api.get<PlaygroundMediaItem[]>(`${BASE}/media`, { params });
  return res.data;
}

/** 본인 미디어 파일을 서빙하는 안정 URL (텐센트 임시 URL 만료 후에도 동작). */
export function mediaFileUrl(mediaId: string): string {
  return `${BASE}/media/${encodeURIComponent(mediaId)}/file`;
}

export interface PlaygroundUsageByModel {
  model: string;
  kind: "text" | "image" | "video";
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface PlaygroundUsageByUser {
  user_id: string;
  user_email: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface PlaygroundUsageReport {
  period_start: string | null;
  period_end: string | null;
  total_cost_usd: number;
  total_requests: number;
  by_model: PlaygroundUsageByModel[];
  by_user: PlaygroundUsageByUser[];
}

export async function getAdminUsage(
  start?: string,
  end?: string,
): Promise<PlaygroundUsageReport> {
  const params: Record<string, string> = {};
  if (start) params.start = start;
  if (end) params.end = end;
  const res = await api.get<PlaygroundUsageReport>(`${BASE}/admin/usage`, {
    params,
  });
  return res.data;
}

// ---------------------------------------------------------------------------
// 본인 한도 (모든 사용자) + admin 한도 관리
// ---------------------------------------------------------------------------

/**
 * 백엔드 Numeric (Decimal) 필드는 JSON 직렬화 시 string 으로 옴.
 * 표시 시점에 항상 `Number(v).toFixed(...)` 로 wrap 한다.
 */
export interface PlaygroundQuotaInfo {
  monthly_quota_usd: number | string;
  current_usage_usd: number | string;
  remaining_usd: number | string;
  period_start: string;
  period_end: string;
}

export async function getMyQuota(): Promise<PlaygroundQuotaInfo> {
  const res = await api.get<PlaygroundQuotaInfo>(`${BASE}/me/quota`);
  return res.data;
}

// ---------------------------------------------------------------------------
// Admin: 세션 모니터링 / 사용자 한도 관리 / 로그 tail
// ---------------------------------------------------------------------------

export interface PlaygroundAdminSession {
  id: string;
  user_id: string;
  user_email: string;
  title: string | null;
  provider: string;
  model: string;
  created_at: string;
  updated_at: string;
}

export interface AdminSessionFilters {
  user_id?: string;
  q?: string;
  limit?: number;
}

export async function adminListSessions(
  filters: AdminSessionFilters = {},
): Promise<PlaygroundAdminSession[]> {
  const params: Record<string, string | number> = {};
  if (filters.user_id && filters.user_id.trim()) {
    params.user_id = filters.user_id.trim();
  }
  if (filters.q && filters.q.trim()) {
    params.q = filters.q.trim();
  }
  params.limit = filters.limit ?? 50;
  const res = await api.get<PlaygroundAdminSession[]>(
    `${BASE}/admin/sessions`,
    { params },
  );
  return res.data;
}

export async function adminGetMessages(
  sessionId: string,
): Promise<PlaygroundMessage[]> {
  const res = await api.get<PlaygroundMessage[]>(
    `${BASE}/admin/sessions/${encodeURIComponent(sessionId)}/messages`,
  );
  return res.data;
}

export interface PlaygroundAdminUserQuota {
  user_id: string;
  user_email: string;
  monthly_quota_usd: number | string;
  current_usage_usd: number | string;
  remaining_usd: number | string;
}

export async function adminGetUserQuotas(): Promise<PlaygroundAdminUserQuota[]> {
  const res = await api.get<PlaygroundAdminUserQuota[]>(
    `${BASE}/admin/users/quota`,
  );
  return res.data;
}

export async function adminUpdateUserQuota(
  userId: string,
  monthly_quota_usd: number,
): Promise<void> {
  await api.put(`${BASE}/admin/users/${encodeURIComponent(userId)}/quota`, {
    monthly_quota_usd,
  });
}

export async function adminGetLogs(tail = 200): Promise<string> {
  const res = await api.get<string>(`${BASE}/admin/logs`, {
    params: { tail },
    responseType: "text",
    transformResponse: [
      (data: unknown) => (typeof data === "string" ? data : String(data ?? "")),
    ],
  });
  return res.data;
}

/**
 * Axios 에러에서 HTTP 402 (한도 초과) 를 감지하는 helper.
 *
 * 각 패널/뷰에서 catch 블록 안에 사용:
 *   if (isQuotaExceededError(err)) {
 *     message.error("이번 달 사용량 한도를 초과했습니다. 관리자에게 문의해주세요");
 *     return;
 *   }
 */
export function isQuotaExceededError(err: unknown): boolean {
  if (typeof err !== "object" || err === null) return false;
  const maybe = err as { response?: { status?: number }; status?: number };
  return maybe.response?.status === 402 || maybe.status === 402;
}

export const QUOTA_EXCEEDED_MESSAGE =
  "이번 달 사용량 한도를 초과했습니다. 관리자에게 문의해주세요";
