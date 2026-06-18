import { useEffect, useRef } from "react";
import { Alert, Empty, Spin, Tag, Typography } from "antd";
import type { ChatMessage } from "../../hooks/usePlaygroundChat";

const { Text } = Typography;

interface ChatStreamProps {
  messages: ChatMessage[];
  sending: boolean;
}

function formatMetricsLine(m: ChatMessage): string | null {
  const { inputTokens, outputTokens, totalTokens, latencyMs } = m.metrics;
  if (
    inputTokens == null &&
    outputTokens == null &&
    totalTokens == null &&
    latencyMs == null
  ) {
    return null;
  }
  const i = inputTokens ?? 0;
  const o = outputTokens ?? 0;
  const t = totalTokens ?? i + o;
  const sec = latencyMs != null ? `${(latencyMs / 1000).toFixed(2)}s` : "-";
  return `${i} / ${o} / ${t} / ${sec}`;
}

/**
 * 중앙 채팅 영역 — 메시지 리스트 + 메시지별 인라인 메트릭.
 *
 * - 새 메시지/스트림 chunk 도착 시 자동 스크롤 (bottom)
 * - user 버블 우측 정렬(보라 hint), assistant 좌측 정렬
 * - 메시지 하단에 input/output/total/time + reasoning(있을 때)
 * - 에러는 inline Alert
 */
export default function ChatStream({ messages, sending }: ChatStreamProps) {
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <Empty
          description={
            <div>
              <div style={{ fontSize: 13 }}>대화를 시작해보세요.</div>
              <div style={{ fontSize: 11, color: "rgba(0,0,0,0.45)", marginTop: 4 }}>
                좌측에서 모델/시스템 프롬프트를 설정한 뒤 아래 입력바에서 메시지를 보냅니다.
              </div>
            </div>
          }
        />
      </div>
    );
  }

  return (
    <div
      style={{
        flex: 1,
        // flex 부모 안에서 내용이 넘쳐도 컨테이너를 늘리지 않고 내부 스크롤되도록.
        minHeight: 0,
        overflowY: "auto",
        padding: "16px 24px",
        display: "flex",
        flexDirection: "column",
        gap: 16,
      }}
    >
      {messages.map((m) => {
        const isUser = m.role === "user";
        const metricsLine = formatMetricsLine(m);
        return (
          <div
            key={m.id}
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: isUser ? "flex-end" : "flex-start",
            }}
          >
            <div
              style={{
                maxWidth: "78%",
                padding: "10px 14px",
                borderRadius: 10,
                background: isUser ? "#f0e7ff" : "#f5f5f7",
                border: isUser ? "1px solid #d3adf7" : "1px solid rgba(0,0,0,0.06)",
                whiteSpace: "pre-wrap",
                wordBreak: "break-word",
                fontSize: 13,
                lineHeight: 1.6,
              }}
            >
              {m.content || (m.streaming ? <Spin size="small" /> : null)}
              {m.streaming && m.content ? (
                <span style={{ marginLeft: 4, opacity: 0.5 }}>▍</span>
              ) : null}
            </div>
            {m.error ? (
              <Alert
                type="error"
                showIcon
                message={m.error}
                style={{ marginTop: 6, maxWidth: "78%" }}
              />
            ) : null}
            <div
              style={{
                marginTop: 4,
                fontSize: 11,
                color: "rgba(0,0,0,0.5)",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              {!isUser && m.metrics.model ? (
                <Tag color="purple" style={{ fontSize: 10, padding: "0 6px", margin: 0 }}>
                  {m.metrics.model}
                </Tag>
              ) : null}
              {metricsLine ? <Text style={{ fontSize: 11 }}>{metricsLine}</Text> : null}
              {m.metrics.reasoningTokens != null && m.metrics.reasoningTokens > 0 ? (
                <Text style={{ fontSize: 11 }}>
                  Reasoning: {m.metrics.reasoningTokens}
                </Text>
              ) : null}
            </div>
          </div>
        );
      })}
      {sending ? null : null}
      <div ref={bottomRef} />
    </div>
  );
}
