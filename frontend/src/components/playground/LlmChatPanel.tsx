import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from "react";
import { Button, Card, Slider, Tooltip, Typography, message } from "antd";
import { BugOutlined, CloudUploadOutlined } from "@ant-design/icons";
import type {
  PlaygroundProvider,
  PlaygroundProviderKey,
  PlaygroundSession,
} from "../../api/playground";
import {
  QUOTA_EXCEEDED_MESSAGE,
  getProviders,
} from "../../api/playground";
import { useChatAttachments } from "../../hooks/useChatAttachments";
import { usePlaygroundChat } from "../../hooks/usePlaygroundChat";
import ChatInputBar from "./ChatInputBar";
import ChatStream from "./ChatStream";
import ModelChipList from "./ModelChipList";
import ModelGrid from "./ModelGrid";
import QuotaIndicator from "./QuotaIndicator";
import SessionList from "./SessionList";
import SystemPromptBox from "./SystemPromptBox";
import UsageCard from "./UsageCard";
import { DEFAULT_MODEL_ID, DEFAULT_PROVIDER_KEY, STATIC_PROVIDERS } from "./providers";

const { Text } = Typography;

const SIDEBAR_WIDTH = 280;

const SECTION_LABEL_STYLE = {
  fontSize: 11,
  letterSpacing: "0.06em",
  color: "rgba(0,0,0,0.45)",
  fontWeight: 600,
  marginBottom: 6,
} as const;

/**
 * LLM Chat 탭 콘텐츠 — 좌측 모델/설정 사이드바 + 중앙 채팅.
 *
 * 백엔드 `/api/playground/providers` 호출이 실패해도 STATIC_PROVIDERS 폴백으로
 * UI는 정상 노출된다.
 */
export default function LlmChatPanel() {
  const [providers, setProviders] = useState<PlaygroundProvider[]>(STATIC_PROVIDERS);
  const [providerKey, setProviderKey] = useState<PlaygroundProviderKey>(DEFAULT_PROVIDER_KEY);
  const [modelId, setModelId] = useState<string>(DEFAULT_MODEL_ID);
  const [systemPrompt, setSystemPrompt] = useState<string>("");
  const [temperature, setTemperature] = useState<number>(0.7);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const data = await getProviders();
        if (!cancelled && Array.isArray(data) && data.length > 0) {
          setProviders(data);
          // 선택된 모델이 응답에서 사라졌다면 첫 enabled 변형으로 보정
          const sel = data.find((p) => p.key === providerKey) ?? data[0];
          if (sel?.enabled) {
            setProviderKey(sel.key);
            if (!sel.variants.some((v) => v.id === modelId)) {
              setModelId(sel.variants[0]?.id ?? DEFAULT_MODEL_ID);
            }
          }
        }
      } catch {
        // 백엔드 미가동이거나 권한 없음 — STATIC_PROVIDERS 유지.
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
    // 마운트 시 1회만.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedProvider = useMemo(
    () => providers.find((p) => p.key === providerKey) ?? providers[0],
    [providers, providerKey],
  );

  const chat = usePlaygroundChat({
    provider: providerKey,
    model: modelId,
    systemPrompt,
    temperature,
  });

  // 첨부 상태는 hook 으로 분리 — ChatInputBar + 채팅 카드 drop zone 이 공유.
  const att = useChatAttachments(chat.sessionId);
  const [isDragging, setIsDragging] = useState(false);
  const dragCounter = useRef(0);

  const onDragEnter = (e: DragEvent<HTMLDivElement>) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    dragCounter.current += 1;
    setIsDragging(true);
  };
  const onDragLeave = (e: DragEvent<HTMLDivElement>) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    dragCounter.current -= 1;
    if (dragCounter.current <= 0) {
      dragCounter.current = 0;
      setIsDragging(false);
    }
  };
  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    if (!e.dataTransfer?.types?.includes("Files")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  };
  const onDrop = async (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    dragCounter.current = 0;
    setIsDragging(false);
    const files = Array.from(e.dataTransfer.files ?? []);
    if (files.length === 0) return;
    await att.addFiles(files);
  };

  // SessionList 갱신 트리거 — 새 세션 생성/삭제 시 증가.
  const [sessionListKey, setSessionListKey] = useState(0);
  const bumpSessionList = useCallback(() => setSessionListKey((k) => k + 1), []);

  // Quota 표시 — sending 이 true→false 로 바뀔 때마다 재조회.
  const [quotaRefreshKey, setQuotaRefreshKey] = useState(0);
  const [prevSending, setPrevSending] = useState(chat.sending);
  useEffect(() => {
    if (prevSending && !chat.sending) {
      setQuotaRefreshKey((k) => k + 1);
    }
    setPrevSending(chat.sending);
  }, [chat.sending, prevSending]);

  // 마지막 assistant 메시지 에러 = 한도 초과 메시지면 토스트 한 번 띄움.
  // (스트리밍 시작 후 onError 가 호출되어 chat.messages 의 마지막 항목에 error 가 박힘.)
  const lastErrorMsg = chat.messages[chat.messages.length - 1]?.error ?? null;
  const [shownQuotaError, setShownQuotaError] = useState<string | null>(null);
  useEffect(() => {
    if (
      lastErrorMsg &&
      lastErrorMsg.includes(QUOTA_EXCEEDED_MESSAGE) &&
      lastErrorMsg !== shownQuotaError
    ) {
      message.error(QUOTA_EXCEEDED_MESSAGE);
      setShownQuotaError(lastErrorMsg);
    }
  }, [lastErrorMsg, shownQuotaError]);

  const onProviderSelect = (key: PlaygroundProviderKey) => {
    const next = providers.find((p) => p.key === key);
    if (!next || !next.enabled) return;
    setProviderKey(key);
    const firstId = next.variants[0]?.id;
    if (firstId) setModelId(firstId);
    chat.resetSession();
  };

  const onModelSelect = (id: string) => {
    if (id === modelId) return;
    setModelId(id);
    chat.resetSession();
  };

  const onSelectSession = useCallback(
    async (s: PlaygroundSession) => {
      // 세션의 provider/model 로 사이드바 동기화.
      setProviderKey(s.provider);
      setModelId(s.model);
      setSystemPrompt(s.system_prompt ?? "");
      setTemperature(Number(s.temperature) || 0.7);
      await chat.loadSession(s);
    },
    [chat],
  );

  const onNewChat = useCallback(() => {
    chat.resetSession();
    bumpSessionList();
  }, [chat, bumpSessionList]);

  // 첫 메시지가 보내져서 sessionId가 새로 생성됐는지 트래킹.
  // chat.sessionId 가 null → 값으로 바뀌면 SessionList 갱신.
  const [lastSeenSessionId, setLastSeenSessionId] = useState<string | null>(null);
  useEffect(() => {
    if (chat.sessionId && chat.sessionId !== lastSeenSessionId) {
      setLastSeenSessionId(chat.sessionId);
      bumpSessionList();
    }
  }, [chat.sessionId, lastSeenSessionId, bumpSessionList]);

  return (
    <div
      style={{
        display: "flex",
        height: "calc(100vh - 220px)",
        minHeight: 560,
        gap: 16,
      }}
    >
      {/* 최좌측: 세션 목록 */}
      <SessionList
        activeSessionId={chat.sessionId}
        onSelect={onSelectSession}
        onNewChat={onNewChat}
        refreshKey={sessionListKey}
      />

      {/* 모델/설정 사이드바 */}
      <div
        style={{
          width: SIDEBAR_WIDTH,
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
          gap: 12,
          overflowY: "auto",
          paddingRight: 4,
        }}
      >
        <div>
          <div style={SECTION_LABEL_STYLE}>LLM MODEL</div>
          <ModelGrid
            providers={providers}
            selectedKey={providerKey}
            onSelect={onProviderSelect}
          />
        </div>

        <div>
          <div style={SECTION_LABEL_STYLE}>{selectedProvider?.name.toUpperCase() ?? ""}</div>
          <ModelChipList
            variants={selectedProvider?.variants ?? []}
            selectedId={modelId}
            onSelect={onModelSelect}
          />
        </div>

        <div>
          <div style={SECTION_LABEL_STYLE}>SYSTEM PROMPT (OPTIONAL)</div>
          <SystemPromptBox value={systemPrompt} onChange={setSystemPrompt} />
        </div>

        <div>
          <div style={SECTION_LABEL_STYLE}>
            TEMPERATURE <Text style={{ color: "rgba(0,0,0,0.65)" }}>· {temperature.toFixed(2)}</Text>
          </div>
          <Slider
            min={0}
            max={1}
            step={0.05}
            value={temperature}
            onChange={(v) => setTemperature(Array.isArray(v) ? v[0] : v)}
            tooltip={{ formatter: (v) => (typeof v === "number" ? v.toFixed(2) : "") }}
          />
        </div>

        <QuotaIndicator refreshKey={quotaRefreshKey} />

        <UsageCard usage={chat.usage} />
      </div>

      {/* 우측 채팅 영역 — 카드 전체가 드롭 zone */}
      <div
        onDragEnter={onDragEnter}
        onDragLeave={onDragLeave}
        onDragOver={onDragOver}
        onDrop={onDrop}
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          minWidth: 0,
          position: "relative",
        }}
      >
        <Card
          size="small"
          styles={{
            body: {
              padding: 0,
              display: "flex",
              flexDirection: "column",
              height: "100%",
              // flex 자식(ChatStream)이 컨테이너를 늘리지 않고 내부 스크롤되도록.
              minHeight: 0,
            },
          }}
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            minWidth: 0,
            // 카드 자체도 부모(고정 height)를 넘기지 않게.
            minHeight: 0,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "10px 24px",
              borderBottom: "1px solid rgba(0,0,0,0.08)",
              flexShrink: 0,
            }}
          >
            <Text strong style={{ fontSize: 13 }}>
              {selectedProvider?.name ?? "Chat"} · {modelId}
            </Text>
            <Tooltip title="Debug 패널은 Phase 2에서 활성화됩니다">
              <Button
                icon={<BugOutlined />}
                size="small"
                onClick={() => message.info("Phase 2에서 활성화")}
              >
                Debug
              </Button>
            </Tooltip>
          </div>

          <ChatStream messages={chat.messages} sending={chat.sending} />

          <ChatInputBar
            onSend={chat.sendMessage}
            onNewChat={chat.resetSession}
            sending={chat.sending}
            model={modelId}
            attachments={att.attachments}
            uploading={att.uploading}
            onAddFiles={att.addFiles}
            onRemoveAttachment={att.remove}
            onAfterSend={att.clear}
          />
        </Card>

        {isDragging && (
          <div
            style={{
              position: "absolute",
              inset: 8,
              border: "2px dashed #1677ff",
              background: "rgba(22, 119, 255, 0.08)",
              borderRadius: 8,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 8,
              pointerEvents: "none",
              zIndex: 10,
              color: "#1677ff",
              fontWeight: 600,
            }}
          >
            <CloudUploadOutlined style={{ fontSize: 36 }} />
            <div>파일을 여기에 놓으세요 — 이미지·PDF·텍스트·DOCX</div>
          </div>
        )}
      </div>
    </div>
  );
}
