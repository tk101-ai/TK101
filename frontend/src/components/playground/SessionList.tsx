import { useEffect, useState } from "react";
import { Button, List, Tag, Typography, Popconfirm, message } from "antd";
import { PlusOutlined, DeleteOutlined } from "@ant-design/icons";
import {
  deleteSession,
  listSessions,
  type PlaygroundSession,
} from "../../api/playground";

const { Text } = Typography;

interface SessionListProps {
  activeSessionId: string | null;
  onSelect: (session: PlaygroundSession) => void;
  onNewChat: () => void;
  /** sendMessage 끝나거나 모델 변경할 때 부모가 호출 → 목록 갱신. */
  refreshKey: number;
}

/**
 * LLM Chat 좌측 세션 목록.
 *
 * - listSessions 로 본인 세션 가져오기 (최신순).
 * - 클릭 → onSelect(session) → 부모가 loadSession 호출.
 * - 휴지통 아이콘 → deleteSession 후 목록 갱신.
 */
export default function SessionList({
  activeSessionId,
  onSelect,
  onNewChat,
  refreshKey,
}: SessionListProps) {
  const [sessions, setSessions] = useState<PlaygroundSession[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      try {
        const data = await listSessions();
        if (!cancelled) setSessions(data);
      } catch {
        // 권한/네트워크 실패 — 빈 목록 유지.
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const handleDelete = async (id: string) => {
    try {
      await deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (activeSessionId === id) onNewChat();
    } catch {
      message.error("세션 삭제 실패");
    }
  };

  return (
    <div
      style={{
        width: 220,
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        height: "100%",
      }}
    >
      <Button
        icon={<PlusOutlined />}
        block
        type="primary"
        onClick={onNewChat}
        size="small"
      >
        새 대화
      </Button>

      <div
        style={{
          fontSize: 11,
          color: "rgba(0,0,0,0.45)",
          letterSpacing: "0.06em",
          fontWeight: 600,
          marginTop: 4,
        }}
      >
        이전 대화 ({sessions.length})
      </div>

      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        <List
          size="small"
          loading={loading}
          dataSource={sessions}
          locale={{ emptyText: "아직 대화가 없습니다" }}
          renderItem={(s) => {
            const isActive = s.id === activeSessionId;
            return (
              <List.Item
                style={{
                  padding: "6px 8px",
                  borderRadius: 6,
                  background: isActive ? "rgba(24,144,255,0.08)" : "transparent",
                  cursor: "pointer",
                  border: isActive
                    ? "1px solid rgba(24,144,255,0.3)"
                    : "1px solid transparent",
                  marginBottom: 4,
                }}
                onClick={() => onSelect(s)}
                actions={[
                  <Popconfirm
                    key="del"
                    title="이 대화를 삭제할까요?"
                    okText="삭제"
                    cancelText="취소"
                    onConfirm={(e) => {
                      e?.stopPropagation();
                      void handleDelete(s.id);
                    }}
                    onCancel={(e) => e?.stopPropagation()}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<DeleteOutlined />}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Popconfirm>,
                ]}
              >
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 2,
                    minWidth: 0,
                    flex: 1,
                  }}
                >
                  <Text
                    style={{ fontSize: 12, fontWeight: 500 }}
                    ellipsis={{ tooltip: s.title ?? "(제목 없음)" }}
                  >
                    {s.title ?? "(제목 없음)"}
                  </Text>
                  <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                    <Tag style={{ fontSize: 10, lineHeight: "16px", padding: "0 4px" }}>
                      {s.model}
                    </Tag>
                  </div>
                </div>
              </List.Item>
            );
          }}
        />
      </div>
    </div>
  );
}
