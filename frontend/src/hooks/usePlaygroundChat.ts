import { useCallback, useRef, useState } from "react";
import {
  createSession,
  getSessionMessages,
  streamChat,
  type CreateSessionBody,
  type PlaygroundChunk,
  type PlaygroundMessage as ApiPlaygroundMessage,
  type PlaygroundSession as ApiPlaygroundSession,
} from "../api/playground";

/**
 * AI Playground 채팅 상태 훅 (T8 Phase 1).
 *
 * - sendMessage(text) → 세션이 없으면 자동 createSession 후 streamChat 호출.
 * - 메시지/메트릭 누적, 진행 중 토큰 합산.
 * - resetSession() 으로 "New Chat" 처리.
 */

export interface ChatMessageMetrics {
  inputTokens: number | null;
  outputTokens: number | null;
  reasoningTokens: number | null;
  cachedTokens: number | null;
  totalTokens: number | null;
  latencyMs: number | null;
  model: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  metrics: ChatMessageMetrics;
  streaming: boolean;
  error?: string | null;
  /** NAS RAG 사용 시 답변에 참고된 회사 문서 출처 경로 목록. */
  sources?: string[];
}

export interface CumulativeUsage {
  totalRequests: number;
  totalInput: number;
  totalOutput: number;
  totalTokens: number;
  cached: number;
  reasoning: number;
  imagesGenerated: number;
  videoSeconds: number;
}

const EMPTY_USAGE: CumulativeUsage = {
  totalRequests: 0,
  totalInput: 0,
  totalOutput: 0,
  totalTokens: 0,
  cached: 0,
  reasoning: 0,
  imagesGenerated: 0,
  videoSeconds: 0,
};

const EMPTY_METRICS: ChatMessageMetrics = {
  inputTokens: null,
  outputTokens: null,
  reasoningTokens: null,
  cachedTokens: null,
  totalTokens: null,
  latencyMs: null,
  model: null,
};

function tempId(prefix: string): string {
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

export interface UsePlaygroundChatArgs {
  provider: CreateSessionBody["provider"];
  model: string;
  systemPrompt: string;
  temperature: number;
  /** true 면 채팅 호출 시 회사 NAS 문서(RAG)를 참고하도록 백엔드에 요청. */
  useNasRag?: boolean;
}

export function usePlaygroundChat(args: UsePlaygroundChatArgs) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [usage, setUsage] = useState<CumulativeUsage>(EMPTY_USAGE);
  const abortRef = useRef<AbortController | null>(null);

  const ensureSession = useCallback(async (): Promise<string> => {
    if (sessionId) return sessionId;
    const created = await createSession({
      provider: args.provider,
      model: args.model,
      system_prompt: args.systemPrompt || null,
      temperature: args.temperature,
    });
    setSessionId(created.id);
    return created.id;
  }, [sessionId, args.provider, args.model, args.systemPrompt, args.temperature]);

  const updateAssistant = useCallback(
    (assistantId: string, updater: (m: ChatMessage) => ChatMessage) => {
      setMessages((prev) => prev.map((m) => (m.id === assistantId ? updater(m) : m)));
    },
    [],
  );

  const sendMessage = useCallback(
    async (text: string, attachmentIds: string[] = []): Promise<void> => {
      const trimmed = text.trim();
      if (!trimmed || sending) return;

      let sid: string;
      try {
        sid = await ensureSession();
      } catch {
        setMessages((prev) => [
          ...prev,
          {
            id: tempId("err"),
            role: "assistant",
            content: "",
            metrics: { ...EMPTY_METRICS },
            streaming: false,
            error: "세션 생성 실패 — 백엔드 미가동일 수 있습니다.",
          },
        ]);
        return;
      }

      const userMsg: ChatMessage = {
        id: tempId("u"),
        role: "user",
        content: trimmed,
        metrics: { ...EMPTY_METRICS },
        streaming: false,
      };
      const assistantId = tempId("a");
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        metrics: { ...EMPTY_METRICS, model: args.model },
        streaming: true,
      };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setSending(true);

      const controller = new AbortController();
      abortRef.current = controller;

      // 이 메시지의 토큰 메트릭은 "마지막 값 유지" 방식으로 받고,
      // 누적 사용량(cumulative)에는 'done' 시점에 단 한 번만 더한다.
      // 백엔드는 OpenAI stream_options.include_usage / Anthropic 종단 usage 로
      // 스트림당 단일 terminal usage 청크만 보내므로 현재 동작은 동일하다.
      // (incremental usage 로 바뀌어도 이중 합산되지 않도록 한 안전장치.)
      const lastUsage = {
        input: 0,
        output: 0,
        total: 0,
        cached: 0,
        reasoning: 0,
      };

      try {
        await streamChat(
          {
            session_id: sid,
            message: trimmed,
            provider: args.provider,
            model: args.model,
            system_prompt: args.systemPrompt || null,
            temperature: args.temperature,
            attachment_ids: attachmentIds.length > 0 ? attachmentIds : undefined,
            use_nas_rag: args.useNasRag || undefined,
          },
          {
            signal: controller.signal,
            onChunk: (chunk: PlaygroundChunk) => {
              if (chunk.type === "text_delta") {
                updateAssistant(assistantId, (m) => ({
                  ...m,
                  content: m.content + chunk.content,
                }));
              } else if (chunk.type === "usage") {
                const inputN = chunk.input ?? 0;
                const outputN = chunk.output ?? 0;
                const reasoningN = chunk.reasoning ?? 0;
                const cachedN = chunk.cached ?? 0;
                const totalN = chunk.total ?? inputN + outputN;
                updateAssistant(assistantId, (m) => ({
                  ...m,
                  metrics: {
                    inputTokens: chunk.input ?? m.metrics.inputTokens,
                    outputTokens: chunk.output ?? m.metrics.outputTokens,
                    reasoningTokens: chunk.reasoning ?? m.metrics.reasoningTokens,
                    cachedTokens: chunk.cached ?? m.metrics.cachedTokens,
                    totalTokens: chunk.total ?? totalN,
                    latencyMs: chunk.latency_ms ?? m.metrics.latencyMs,
                    model: chunk.model ?? m.metrics.model,
                  },
                }));
                // 누적엔 더하지 않고 "마지막 값"만 기록 — 'done' 에서 한 번 반영.
                lastUsage.input = inputN;
                lastUsage.output = outputN;
                lastUsage.total = totalN;
                lastUsage.cached = cachedN;
                lastUsage.reasoning = reasoningN;
              } else if (chunk.type === "sources") {
                updateAssistant(assistantId, (m) => ({
                  ...m,
                  sources: chunk.sources,
                }));
              } else if (chunk.type === "done") {
                updateAssistant(assistantId, (m) => ({ ...m, streaming: false }));
                setUsage((prev) => ({
                  ...prev,
                  totalRequests: prev.totalRequests + 1,
                  totalInput: prev.totalInput + lastUsage.input,
                  totalOutput: prev.totalOutput + lastUsage.output,
                  totalTokens: prev.totalTokens + lastUsage.total,
                  cached: prev.cached + lastUsage.cached,
                  reasoning: prev.reasoning + lastUsage.reasoning,
                }));
              } else if (chunk.type === "error") {
                updateAssistant(assistantId, (m) => ({
                  ...m,
                  streaming: false,
                  error: chunk.message,
                }));
              }
            },
            onError: (err) => {
              updateAssistant(assistantId, (m) => ({
                ...m,
                streaming: false,
                error: err.message || "스트림 오류",
              }));
            },
            onClose: () => {
              updateAssistant(assistantId, (m) =>
                m.streaming ? { ...m, streaming: false } : m,
              );
            },
          },
        );
      } catch (err: unknown) {
        // SSE 가 열리기 전(네트워크 실패 등) streamChat 이 reject 하면
        // onError/onClose 가 호출되지 않아 어시스턴트 버블이 streaming 에 묶인다.
        // 여기서 errored 로 표시해 입력/버블을 풀어준다.
        const msg = err instanceof Error ? err.message : "스트림 오류";
        updateAssistant(assistantId, (m) => ({
          ...m,
          streaming: false,
          error: m.error ?? msg,
        }));
      } finally {
        // 성공/실패/예외 무관하게 항상 잠금 해제 + abort 정리.
        setSending(false);
        abortRef.current = null;
      }
    },
    [
      sending,
      ensureSession,
      args.provider,
      args.model,
      args.systemPrompt,
      args.temperature,
      args.useNasRag,
      updateAssistant,
    ],
  );

  const resetSession = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    setSessionId(null);
    setSending(false);
  }, []);

  /** 기존 세션을 화면에 복원. 메시지 fetch 후 채팅 패널에 표시. */
  const loadSession = useCallback(
    async (session: ApiPlaygroundSession): Promise<void> => {
      abortRef.current?.abort();
      abortRef.current = null;
      setSending(false);
      setSessionId(session.id);
      try {
        const apiMessages = await getSessionMessages(session.id);
        const restored: ChatMessage[] = apiMessages.map(
          (m: ApiPlaygroundMessage): ChatMessage => ({
            id: m.id,
            role: m.role,
            content: m.content,
            metrics: {
              inputTokens: m.input_tokens,
              outputTokens: m.output_tokens,
              reasoningTokens: m.reasoning_tokens,
              cachedTokens: m.cached_tokens,
              totalTokens: m.total_tokens,
              latencyMs: m.latency_ms,
              model: m.model,
            },
            streaming: false,
          }),
        );
        setMessages(restored);
      } catch {
        // 세션은 존재하지만 메시지 fetch 실패 — 빈 화면 유지.
        setMessages([]);
      }
    },
    [],
  );

  return {
    messages,
    sending,
    usage,
    sessionId,
    sendMessage,
    resetSession,
    loadSession,
  };
}
