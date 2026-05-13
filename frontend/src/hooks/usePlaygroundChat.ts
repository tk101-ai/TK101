import { useCallback, useRef, useState } from "react";
import {
  createSession,
  streamChat,
  type CreateSessionBody,
  type PlaygroundChunk,
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
    async (text: string): Promise<void> => {
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

      await streamChat(
        { session_id: sid, content: trimmed },
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
              setUsage((prev) => ({
                ...prev,
                totalInput: prev.totalInput + inputN,
                totalOutput: prev.totalOutput + outputN,
                totalTokens: prev.totalTokens + totalN,
                cached: prev.cached + cachedN,
                reasoning: prev.reasoning + reasoningN,
              }));
            } else if (chunk.type === "done") {
              updateAssistant(assistantId, (m) => ({ ...m, streaming: false }));
              setUsage((prev) => ({ ...prev, totalRequests: prev.totalRequests + 1 }));
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

      setSending(false);
      abortRef.current = null;
    },
    [sending, ensureSession, args.model, updateAssistant],
  );

  const resetSession = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setMessages([]);
    setSessionId(null);
    setSending(false);
  }, []);

  return {
    messages,
    sending,
    usage,
    sessionId,
    sendMessage,
    resetSession,
  };
}
