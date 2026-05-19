import { useEffect, useMemo, useRef, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Checkbox,
  Input,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { ClearOutlined, SendOutlined } from "@ant-design/icons";
import {
  createSession,
  getProviders,
  streamChat,
  type PlaygroundChunk,
  type PlaygroundProvider,
} from "../../api/playground";
import { STATIC_PROVIDERS } from "./providers";

const { Title, Paragraph, Text } = Typography;

interface ModelLane {
  /** flat 모델 id, e.g. "gemini-2.5-flash" */
  modelId: string;
  /** UI 라벨, e.g. "Gemini 2.5 Flash" */
  label: string;
  /** provider key for session create body */
  providerKey: string;
  /** 세션 id (sendMessage 첫 호출 시 채워짐) */
  sessionId: string | null;
  /** 현재 응답 텍스트 누적 */
  content: string;
  /** 사용 메트릭 */
  inputTokens: number | null;
  outputTokens: number | null;
  latencyMs: number | null;
  /** 진행 상태 */
  streaming: boolean;
  error: string | null;
}

/**
 * 멀티모델 동시 전송 패널 (사용자 요구 #8 추천 — "동시 비교").
 *
 * UX:
 *   1. 상단에서 모델 N개 체크박스로 선택 (기본 단일 모델 → 사용자가 원할 때 활성화).
 *   2. 한 번의 프롬프트를 N개 모델에 병렬로 전송. 응답은 컬럼별로 동시 스트림.
 *   3. 비용/토큰은 백엔드가 단가표 적용해 자동 집계 (관리자 페이지에서 확인).
 *
 * 비용 주의:
 *   - N개 모델에 동시 전송 → N배 비용. 화면 상단에 안내 노출.
 *   - 기본 비활성. 사용자가 토글 의도적으로 활성화.
 */
export default function ComparePanel() {
  const [providers, setProviders] = useState<PlaygroundProvider[]>(STATIC_PROVIDERS);
  const [selected, setSelected] = useState<string[]>([]);
  const [prompt, setPrompt] = useState("");
  const [lanes, setLanes] = useState<ModelLane[]>([]);
  const [sending, setSending] = useState(false);
  const abortsRef = useRef<AbortController[]>([]);

  // provider 목록 fetch.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getProviders();
        if (!cancelled && Array.isArray(data) && data.length > 0) {
          setProviders(data);
        }
      } catch {
        // STATIC fallback 유지.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // 모든 enabled 모델을 평면 옵션으로 (provider 어울려 표시).
  const allOptions = useMemo(() => {
    const list: Array<{ id: string; label: string; provider: string }> = [];
    for (const p of providers) {
      if (!p.enabled) continue;
      for (const v of p.variants) {
        list.push({ id: v.id, label: `${p.name} · ${v.label}`, provider: p.key });
      }
    }
    return list;
  }, [providers]);

  const toggleModel = (id: string, checked: boolean) => {
    setSelected((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)));
  };

  const reset = () => {
    abortsRef.current.forEach((c) => c.abort());
    abortsRef.current = [];
    setLanes([]);
    setSending(false);
  };

  const send = async () => {
    const trimmed = prompt.trim();
    if (!trimmed) return;
    if (selected.length === 0) {
      message.warning("모델을 1개 이상 선택해주세요");
      return;
    }
    if (sending) return;

    // 1) 각 모델별로 빈 lane 만들고, 세션 동시 생성.
    const meta = selected
      .map((id) => allOptions.find((o) => o.id === id))
      .filter((x): x is { id: string; label: string; provider: string } => !!x);

    setSending(true);
    const initialLanes: ModelLane[] = meta.map((m) => ({
      modelId: m.id,
      label: m.label,
      providerKey: m.provider,
      sessionId: null,
      content: "",
      inputTokens: null,
      outputTokens: null,
      latencyMs: null,
      streaming: true,
      error: null,
    }));
    setLanes(initialLanes);

    // 세션 생성 병렬.
    const sessionResults = await Promise.allSettled(
      meta.map((m) =>
        createSession({
          provider: m.provider,
          model: m.id,
          system_prompt: null,
          temperature: 0.7,
          title: trimmed.slice(0, 40),
        }),
      ),
    );

    // 2) 각 lane 에 sessionId 박고 streamChat 병렬 시작.
    abortsRef.current = meta.map(() => new AbortController());
    const t0 = performance.now();

    await Promise.all(
      meta.map(async (m, idx) => {
        const sr = sessionResults[idx];
        if (sr.status === "rejected") {
          setLanes((prev) =>
            prev.map((l, i) =>
              i === idx
                ? { ...l, error: "세션 생성 실패", streaming: false }
                : l,
            ),
          );
          return;
        }
        const sid = sr.value.id;
        setLanes((prev) =>
          prev.map((l, i) => (i === idx ? { ...l, sessionId: sid } : l)),
        );

        await streamChat(
          {
            session_id: sid,
            message: trimmed,
            provider: m.provider,
            model: m.id,
            system_prompt: null,
            temperature: 0.7,
          },
          {
            signal: abortsRef.current[idx].signal,
            onChunk: (chunk: PlaygroundChunk) => {
              if (chunk.type === "text_delta") {
                setLanes((prev) =>
                  prev.map((l, i) =>
                    i === idx ? { ...l, content: l.content + chunk.content } : l,
                  ),
                );
              } else if (chunk.type === "usage") {
                setLanes((prev) =>
                  prev.map((l, i) =>
                    i === idx
                      ? {
                          ...l,
                          inputTokens: chunk.input ?? l.inputTokens,
                          outputTokens: chunk.output ?? l.outputTokens,
                          latencyMs: chunk.latency_ms ?? l.latencyMs,
                        }
                      : l,
                  ),
                );
              } else if (chunk.type === "done") {
                setLanes((prev) =>
                  prev.map((l, i) =>
                    i === idx
                      ? {
                          ...l,
                          streaming: false,
                          latencyMs: l.latencyMs ?? Math.round(performance.now() - t0),
                        }
                      : l,
                  ),
                );
              } else if (chunk.type === "error") {
                setLanes((prev) =>
                  prev.map((l, i) =>
                    i === idx
                      ? { ...l, streaming: false, error: chunk.message }
                      : l,
                  ),
                );
              }
            },
            onError: (err) =>
              setLanes((prev) =>
                prev.map((l, i) =>
                  i === idx
                    ? { ...l, streaming: false, error: err.message || "스트림 오류" }
                    : l,
                ),
              ),
            onClose: () =>
              setLanes((prev) =>
                prev.map((l, i) => (i === idx ? { ...l, streaming: false } : l)),
              ),
          },
        );
      }),
    );

    setSending(false);
  };

  return (
    <div style={{ maxWidth: 1480 }}>
      <div style={{ marginBottom: 12 }}>
        <Title level={4} style={{ margin: 0 }}>
          비교 모드 — 같은 프롬프트를 여러 모델에 동시 전송
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0", fontSize: 12 }}>
          N개 모델 선택 → 한 번 보내면 컬럼별로 동시 응답. 비용은 N배 발생하니
          꼭 필요한 경우에만 사용해주세요.
        </Paragraph>
      </div>

      <Card size="small" style={{ marginBottom: 12 }}>
        <div style={{ marginBottom: 8 }}>
          <Text strong style={{ fontSize: 12 }}>모델 선택 ({selected.length}개)</Text>
        </div>
        <Space wrap>
          {allOptions.map((o) => (
            <Checkbox
              key={o.id}
              checked={selected.includes(o.id)}
              onChange={(e) => toggleModel(o.id, e.target.checked)}
            >
              {o.label}
            </Checkbox>
          ))}
        </Space>
      </Card>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Space.Compact style={{ width: "100%" }}>
          <Input.TextArea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="모든 선택된 모델에게 보낼 프롬프트"
            autoSize={{ minRows: 2, maxRows: 6 }}
            disabled={sending}
          />
        </Space.Compact>
        <div style={{ marginTop: 8, display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <Button icon={<ClearOutlined />} onClick={reset} disabled={sending}>
            초기화
          </Button>
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={send}
            loading={sending}
          >
            전송
          </Button>
        </div>
      </Card>

      {lanes.length === 0 ? (
        <Alert
          type="info"
          showIcon
          message="선택한 모델들에게 동시 전송한 결과가 여기 컬럼으로 표시됩니다"
        />
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${Math.min(lanes.length, 4)}, minmax(0, 1fr))`,
            gap: 12,
          }}
        >
          {lanes.map((l) => (
            <Card
              key={l.modelId}
              size="small"
              title={
                <Space>
                  <Tag>{l.label}</Tag>
                  {l.streaming && <Tag color="processing">생성 중</Tag>}
                  {!l.streaming && !l.error && <Tag color="success">완료</Tag>}
                  {l.error && <Tag color="error">실패</Tag>}
                </Space>
              }
              extra={
                l.inputTokens !== null || l.outputTokens !== null ? (
                  <Text style={{ fontSize: 11, color: "rgba(0,0,0,0.45)" }}>
                    {l.inputTokens ?? 0} → {l.outputTokens ?? 0}t
                    {l.latencyMs ? ` · ${l.latencyMs}ms` : ""}
                  </Text>
                ) : null
              }
            >
              {l.error ? (
                <Alert type="error" showIcon message={l.error} />
              ) : (
                <Paragraph
                  style={{
                    whiteSpace: "pre-wrap",
                    fontSize: 13,
                    margin: 0,
                    minHeight: 80,
                  }}
                >
                  {l.content || (l.streaming ? "…" : "")}
                </Paragraph>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
