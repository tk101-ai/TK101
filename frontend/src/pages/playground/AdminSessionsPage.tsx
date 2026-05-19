import { useEffect, useState } from "react";
import {
  Button,
  Card,
  Drawer,
  Empty,
  Input,
  Space,
  Spin,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import {
  adminGetMessages,
  adminListSessions,
  type PlaygroundAdminSession,
  type PlaygroundMessage,
} from "../../api/playground";

const { Title, Paragraph, Text } = Typography;

const ROLE_COLOR: Record<PlaygroundMessage["role"], string> = {
  user: "blue",
  assistant: "green",
  system: "default",
};

const ROLE_LABEL: Record<PlaygroundMessage["role"], string> = {
  user: "USER",
  assistant: "ASSISTANT",
  system: "SYSTEM",
};

/**
 * Playground 세션 모니터링 (admin 전용).
 *
 * - 사용자 id / 검색어 (q) 로 세션 검색.
 * - 행 클릭 → 우측 Drawer 에 메시지 detail.
 */
export default function AdminSessionsPage() {
  const [userId, setUserId] = useState("");
  const [query, setQuery] = useState("");
  const [sessions, setSessions] = useState<PlaygroundAdminSession[]>([]);
  const [loading, setLoading] = useState(false);

  const [drawerSession, setDrawerSession] = useState<PlaygroundAdminSession | null>(
    null,
  );
  const [drawerMessages, setDrawerMessages] = useState<PlaygroundMessage[]>([]);
  const [drawerLoading, setDrawerLoading] = useState(false);

  const fetchSessions = async () => {
    setLoading(true);
    try {
      const data = await adminListSessions({
        user_id: userId || undefined,
        q: query || undefined,
        limit: 50,
      });
      setSessions(data);
    } catch {
      message.error("세션 조회 실패 (admin 권한 필요)");
      setSessions([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchSessions();
    // 마운트 시 1회만 자동 로드 — 이후는 명시적 버튼.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openDetail = async (s: PlaygroundAdminSession) => {
    setDrawerSession(s);
    setDrawerLoading(true);
    setDrawerMessages([]);
    try {
      const data = await adminGetMessages(s.id);
      setDrawerMessages(data);
    } catch {
      message.error("메시지 조회 실패");
    } finally {
      setDrawerLoading(false);
    }
  };

  const columns: ColumnsType<PlaygroundAdminSession> = [
    {
      title: "사용자",
      dataIndex: "user_email",
      width: 220,
      render: (v: string) => <Text style={{ fontSize: 12 }}>{v}</Text>,
    },
    {
      title: "제목",
      dataIndex: "title",
      render: (v: string | null) =>
        v ? (
          <Text style={{ fontSize: 12 }}>{v}</Text>
        ) : (
          <Text type="secondary" style={{ fontSize: 12 }}>
            (제목 없음)
          </Text>
        ),
    },
    {
      title: "모델",
      dataIndex: "model",
      width: 200,
      render: (v: string) => (
        <Text code style={{ fontSize: 11 }}>
          {v}
        </Text>
      ),
    },
    {
      title: "생성일시",
      dataIndex: "created_at",
      width: 170,
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 11 }}>
          {v?.replace("T", " ").slice(0, 19) ?? ""}
        </Text>
      ),
    },
    {
      title: "작업",
      key: "actions",
      width: 100,
      render: (_, record) => (
        <Button
          size="small"
          type="link"
          onClick={(e) => {
            e.stopPropagation();
            void openDetail(record);
          }}
        >
          보기
        </Button>
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 1400 }}>
      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          Playground 세션 모니터링
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0", fontSize: 12 }}>
          전체 사용자의 LLM 채팅 세션을 검색·열람합니다 (admin 전용).
        </Paragraph>
      </div>

      <Card size="small" style={{ marginBottom: 12 }}>
        <Space wrap>
          <Input
            placeholder="사용자 ID 또는 이메일"
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            style={{ width: 240 }}
            allowClear
          />
          <Input
            placeholder="제목·내용 검색"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onPressEnter={() => void fetchSessions()}
            prefix={<SearchOutlined style={{ color: "rgba(0,0,0,0.35)" }} />}
            style={{ width: 260 }}
            allowClear
          />
          <Button
            type="primary"
            icon={<SearchOutlined />}
            onClick={() => void fetchSessions()}
            loading={loading}
          >
            검색
          </Button>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              setUserId("");
              setQuery("");
              setTimeout(() => void fetchSessions(), 0);
            }}
          >
            초기화
          </Button>
        </Space>
      </Card>

      <Card size="small">
        <Table
          size="small"
          rowKey="id"
          columns={columns}
          dataSource={sessions}
          loading={loading}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          onRow={(record) => ({
            onClick: () => void openDetail(record),
            style: { cursor: "pointer" },
          })}
        />
      </Card>

      <Drawer
        title={
          drawerSession ? (
            <div>
              <div style={{ fontWeight: 600 }}>
                {drawerSession.title ?? "(제목 없음)"}
              </div>
              <Text type="secondary" style={{ fontSize: 11 }}>
                {drawerSession.user_email} · {drawerSession.model}
              </Text>
            </div>
          ) : (
            "메시지"
          )
        }
        width={640}
        open={drawerSession !== null}
        onClose={() => {
          setDrawerSession(null);
          setDrawerMessages([]);
        }}
        destroyOnClose
      >
        {drawerLoading ? (
          <div style={{ textAlign: "center", padding: 40 }}>
            <Spin />
          </div>
        ) : drawerMessages.length === 0 ? (
          <Empty description="메시지가 없습니다" />
        ) : (
          <Space direction="vertical" size={12} style={{ width: "100%" }}>
            {drawerMessages.map((m) => (
              <Card key={m.id} size="small">
                <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
                  <Tag color={ROLE_COLOR[m.role]}>{ROLE_LABEL[m.role]}</Tag>
                  {m.model && (
                    <Text code style={{ fontSize: 11 }}>
                      {m.model}
                    </Text>
                  )}
                  <Text type="secondary" style={{ fontSize: 11, marginLeft: "auto" }}>
                    {m.created_at?.replace("T", " ").slice(0, 19) ?? ""}
                  </Text>
                </div>
                <Paragraph
                  style={{
                    fontSize: 13,
                    whiteSpace: "pre-wrap",
                    margin: 0,
                  }}
                >
                  {m.content}
                </Paragraph>
                {(m.input_tokens !== null ||
                  m.output_tokens !== null ||
                  m.latency_ms !== null) && (
                  <div style={{ marginTop: 6, fontSize: 11 }}>
                    <Text type="secondary">
                      {m.input_tokens !== null && (
                        <>in {m.input_tokens.toLocaleString()} · </>
                      )}
                      {m.output_tokens !== null && (
                        <>out {m.output_tokens.toLocaleString()} · </>
                      )}
                      {m.latency_ms !== null && <>{m.latency_ms}ms</>}
                    </Text>
                  </div>
                )}
              </Card>
            ))}
          </Space>
        )}
      </Drawer>
    </div>
  );
}
