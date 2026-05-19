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

export async function listSessions(): Promise<PlaygroundSession[]> {
  const res = await api.get<PlaygroundSession[]>(`${BASE}/sessions`);
  return res.data;
}

export async function deleteSession(id: string): Promise<void> {
  await api.delete(`${BASE}/sessions/${id}`);
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

export async function describeTask(
  kind: "image" | "video",
  taskId: string,
): Promise<PlaygroundTaskStatus> {
  const res = await api.get<PlaygroundTaskStatus>(
    `${BASE}/tasks/${kind}/${encodeURIComponent(taskId)}`,
  );
  return res.data;
}
