import { useEffect, useMemo, useRef, useState } from "react";
import {
  Button,
  Dropdown,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Tag,
  Typography,
  message,
} from "antd";
import {
  DeleteOutlined,
  DownloadOutlined,
  EditOutlined,
  MoreOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import {
  deleteSession,
  exportSession,
  listSessions,
  patchSession,
  type PlaygroundSession,
} from "../../api/playground";

const { Text } = Typography;

const SEARCH_DEBOUNCE_MS = 200;

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
 * - 상단 검색 input (200ms debounce) → listSessions(q) 호출.
 * - 각 카드 우상단 점-3개 메뉴: 수정 / 내보내기.
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
  const [searchInput, setSearchInput] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");

  // 검색어 debounce.
  const debounceRef = useRef<number | null>(null);
  useEffect(() => {
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(() => {
      setDebouncedQuery(searchInput);
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
      }
    };
  }, [searchInput]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      try {
        const q = debouncedQuery.trim();
        const data = await listSessions(q.length > 0 ? q : undefined);
        if (!cancelled) setSessions(data);
      } catch {
        // 권한/네트워크 실패 — 빈 목록 유지.
        if (!cancelled) setSessions([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [refreshKey, debouncedQuery]);

  const [editTarget, setEditTarget] = useState<PlaygroundSession | null>(null);
  const [editForm] = Form.useForm<{ title: string }>();
  const [editSaving, setEditSaving] = useState(false);

  const refresh = useMemo(
    () => async () => {
      try {
        const q = debouncedQuery.trim();
        const data = await listSessions(q.length > 0 ? q : undefined);
        setSessions(data);
      } catch {
        // ignore
      }
    },
    [debouncedQuery],
  );

  const handleDelete = async (id: string) => {
    try {
      await deleteSession(id);
      setSessions((prev) => prev.filter((s) => s.id !== id));
      if (activeSessionId === id) onNewChat();
    } catch {
      message.error("세션 삭제 실패");
    }
  };

  const openEdit = (s: PlaygroundSession) => {
    setEditTarget(s);
    editForm.setFieldsValue({ title: s.title ?? "" });
  };

  const submitEdit = async () => {
    if (!editTarget) return;
    try {
      const values = await editForm.validateFields();
      setEditSaving(true);
      await patchSession(editTarget.id, { title: values.title });
      message.success("세션 제목이 변경되었습니다");
      setEditTarget(null);
      void refresh();
    } catch (err: unknown) {
      if ((err as { errorFields?: unknown }).errorFields) {
        // form validation error — Modal 유지.
        return;
      }
      message.error("세션 수정 실패");
    } finally {
      setEditSaving(false);
    }
  };

  const handleExport = async (s: PlaygroundSession) => {
    try {
      const text = await exportSession(s.id, "md");
      const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const safeTitle = (s.title ?? "session")
        .replace(/[\\/:*?"<>|]/g, "_")
        .slice(0, 80);
      a.href = url;
      a.download = `${safeTitle}-${s.id.slice(0, 8)}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch {
      message.error("세션 내보내기 실패");
    }
  };

  return (
    <div
      style={{
        width: 240,
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

      <Input
        size="small"
        prefix={<SearchOutlined style={{ color: "rgba(0,0,0,0.35)" }} />}
        placeholder="제목 검색"
        value={searchInput}
        onChange={(e) => setSearchInput(e.target.value)}
        allowClear
      />

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
                  <Dropdown
                    key="menu"
                    trigger={["click"]}
                    menu={{
                      items: [
                        {
                          key: "edit",
                          icon: <EditOutlined />,
                          label: "제목 수정",
                          onClick: ({ domEvent }) => {
                            domEvent.stopPropagation();
                            openEdit(s);
                          },
                        },
                        {
                          key: "export",
                          icon: <DownloadOutlined />,
                          label: "내보내기 (.md)",
                          onClick: ({ domEvent }) => {
                            domEvent.stopPropagation();
                            void handleExport(s);
                          },
                        },
                      ],
                    }}
                  >
                    <Button
                      type="text"
                      size="small"
                      icon={<MoreOutlined />}
                      onClick={(e) => e.stopPropagation()}
                    />
                  </Dropdown>,
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

      <Modal
        title="세션 제목 수정"
        open={editTarget !== null}
        onCancel={() => setEditTarget(null)}
        onOk={() => void submitEdit()}
        confirmLoading={editSaving}
        okText="저장"
        cancelText="취소"
        destroyOnClose
      >
        <Form form={editForm} layout="vertical" preserve={false}>
          <Form.Item
            name="title"
            label="제목"
            rules={[
              { required: true, message: "제목을 입력하세요" },
              { max: 200, message: "200자 이내로 입력하세요" },
            ]}
          >
            <Input placeholder="새 제목" autoFocus />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
