import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  Popconfirm,
  Row,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  KeyOutlined,
  LoginOutlined,
  LogoutOutlined,
  PlusOutlined,
  ReloadOutlined,
  SyncOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import {
  PERSONA_ROLE_LABEL,
  PERSONA_ROLE_TAG_COLOR,
  deletePersona,
  listPersonas,
  logoutPersona,
  syncPersona,
  type PersonaOut,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";
import { useAuth } from "../../hooks/useAuth";
import PersonaBusinessNameModal from "../../components/distribution/PersonaBusinessNameModal";
import PersonaCreateModal from "../../components/distribution/PersonaCreateModal";
import PersonaCredentialsModal from "../../components/distribution/PersonaCredentialsModal";
import PersonaLoginModal from "../../components/distribution/PersonaLoginModal";

const { Title, Paragraph, Text } = Typography;

/**
 * 텔레그램 페르소나 관리 페이지 (T9 신사업유통 Phase A — admin 전용).
 *
 * - 등록된 페르소나 목록 + 통계 카드 (전체/로그인됨/자격증명만/미설정)
 * - 새 페르소나 등록 모달 (api_id/api_hash 입력)
 * - SMS 2단계 로그인 모달 (init → verify, 422 → 2FA 비밀번호)
 * - 로그아웃 / 삭제 액션
 *
 * `active` Switch 는 PATCH 연결 전이라 disabled.
 */

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dayjs(iso).format("YYYY-MM-DD HH:mm");
}

interface PersonaStatusBadgeProps {
  persona: PersonaOut;
}

function PersonaStatusBadge({ persona }: PersonaStatusBadgeProps) {
  if (persona.is_logged_in) {
    return <Tag color="green">✅ 로그인됨</Tag>;
  }
  if (persona.has_credentials) {
    return <Tag color="gold">🔑 자격증명 등록됨</Tag>;
  }
  return <Tag>❌ 미설정</Tag>;
}

export default function PersonasPage() {
  // 페르소나 관리(등록/자격증명/로그인/동기화/로그아웃/삭제)는 백엔드에서
  // require_admin 으로 막혀 있다(신사업유통 위험 작업). 일반 member 에게는
  // 해당 버튼/컬럼을 숨겨 403 혼란을 막는다(목록 조회는 허용).
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [data, setData] = useState<PersonaOut[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [createOpen, setCreateOpen] = useState<boolean>(false);
  const [loginTarget, setLoginTarget] = useState<PersonaOut | null>(null);
  const [credsTarget, setCredsTarget] = useState<PersonaOut | null>(null);
  const [nameEditTarget, setNameEditTarget] = useState<PersonaOut | null>(null);
  const [syncingId, setSyncingId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const items = await listPersonas();
      setData(items);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "페르소나 목록 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const run = async () => {
      await fetchData();
    };
    void run();
  }, [fetchData]);

  const stats = useMemo(() => {
    let loggedIn = 0;
    let credOnly = 0;
    let unset = 0;
    for (const p of data) {
      if (p.is_logged_in) loggedIn += 1;
      else if (p.has_credentials) credOnly += 1;
      else unset += 1;
    }
    return { total: data.length, loggedIn, credOnly, unset };
  }, [data]);

  const handleLogout = async (persona: PersonaOut) => {
    try {
      await logoutPersona(persona.id);
      message.success(`${persona.account_label} 로그아웃 완료`);
      await fetchData();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "로그아웃 실패"));
    }
  };

  const handleSync = async (persona: PersonaOut) => {
    setSyncingId(persona.id);
    try {
      const updated = await syncPersona(persona.id);
      message.success(
        `${persona.account_label} 정보 동기화 완료 — 표시명 "${updated.display_name}"`,
      );
      await fetchData();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "정보 동기화 실패"));
    } finally {
      setSyncingId(null);
    }
  };

  const handleDelete = async (persona: PersonaOut) => {
    try {
      await deletePersona(persona.id);
      message.success(`${persona.account_label} 삭제 완료`);
      await fetchData();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "삭제 실패"));
    }
  };

  const handleCreated = async () => {
    await fetchData();
  };

  const handleLoginSuccess = async () => {
    await fetchData();
  };

  const columns: ColumnsType<PersonaOut> = [
    {
      title: "라벨",
      dataIndex: "account_label",
      width: 200,
      render: (label: string, record: PersonaOut) => (
        <Space size={6} direction="vertical">
          <Text strong>{label}</Text>
          <Tag color={PERSONA_ROLE_TAG_COLOR[record.role]}>
            {PERSONA_ROLE_LABEL[record.role]}
          </Tag>
        </Space>
      ),
    },
    {
      title: "사업자명",
      dataIndex: "business_name",
      width: 180,
      render: (v: string | null) =>
        v ? <Text strong>{v}</Text> : <Text type="secondary">—</Text>,
    },
    {
      title: "표시명 (연동 계정)",
      dataIndex: "display_name",
      width: 200,
      render: (v: string, record: PersonaOut) => (
        <Space size={2} direction="vertical">
          <Text>{v || "—"}</Text>
          {record.telegram_username ? (
            <Text
              type="secondary"
              copyable={{ text: `@${record.telegram_username}` }}
              style={{ fontSize: 12, fontFamily: "monospace" }}
            >
              @{record.telegram_username}
            </Text>
          ) : (
            <Text type="secondary" style={{ fontSize: 12 }}>
              @username 없음
            </Text>
          )}
        </Space>
      ),
    },
    {
      title: "폰번호",
      dataIndex: "telegram_phone",
      width: 160,
      render: (v: string) => (
        <span style={{ fontFamily: "monospace", fontSize: 13 }}>{v}</span>
      ),
    },
    {
      title: "상태",
      key: "status",
      width: 160,
      render: (_: unknown, record: PersonaOut) => (
        <PersonaStatusBadge persona={record} />
      ),
    },
    {
      title: "최근 동기화",
      dataIndex: "last_login_at",
      width: 160,
      render: (v: string | null) => (
        <Tooltip title="로그인 또는 정보 동기화로 연동 계정 정보를 마지막으로 최신화한 시각">
          <Text type={v ? undefined : "secondary"} style={{ fontSize: 12 }}>
            {formatDate(v)}
          </Text>
        </Tooltip>
      ),
    },
    {
      title: "일일 한도",
      dataIndex: "daily_msg_limit",
      width: 100,
      align: "right" as const,
      render: (v: number) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{v}</span>
      ),
    },
    {
      title: "활성",
      dataIndex: "active",
      width: 90,
      render: (v: boolean) => (
        <Tooltip title="활성 토글은 추후 PATCH 연결 예정">
          <Switch
            checked={v}
            disabled
            checkedChildren="활성"
            unCheckedChildren="비활성"
          />
        </Tooltip>
      ),
    },
    {
      title: "작업",
      key: "actions",
      width: 360,
      render: (_: unknown, record: PersonaOut) => (
        <Space size={4} wrap>
          <Tooltip title="사업자명 / 표시명 편집">
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => setNameEditTarget(record)}
            >
              사업자명
            </Button>
          </Tooltip>
          <Tooltip title={record.has_credentials ? "api_id/api_hash 회전" : "자격증명 입력"}>
            <Button
              type="link"
              size="small"
              icon={<KeyOutlined />}
              onClick={() => setCredsTarget(record)}
            >
              자격증명
            </Button>
          </Tooltip>
          {record.has_credentials && !record.is_logged_in && (
            <Tooltip title="SMS 인증으로 로그인">
              <Button
                type="link"
                size="small"
                icon={<LoginOutlined />}
                onClick={() => setLoginTarget(record)}
              >
                로그인
              </Button>
            </Tooltip>
          )}
          {record.is_logged_in && (
            <Tooltip title="재로그인 없이 연동된 텔레그램 계정의 이름/@username 을 최신화">
              <Button
                type="link"
                size="small"
                icon={<SyncOutlined spin={syncingId === record.id} />}
                loading={syncingId === record.id}
                onClick={() => handleSync(record)}
              >
                정보 동기화
              </Button>
            </Tooltip>
          )}
          {record.is_logged_in && (
            <Popconfirm
              title="이 페르소나를 로그아웃할까요?"
              description="세션이 종료되어 메시지 송신을 멈춥니다."
              okText="로그아웃"
              cancelText="취소"
              onConfirm={() => handleLogout(record)}
            >
              <Tooltip title="텔레그램 세션 종료">
                <Button
                  type="link"
                  size="small"
                  icon={<LogoutOutlined />}
                >
                  로그아웃
                </Button>
              </Tooltip>
            </Popconfirm>
          )}
          <Popconfirm
            title="이 페르소나를 삭제할까요?"
            description={
              <span>
                자격증명·세션·대화 이력이 모두 제거됩니다.
                <br />이 작업은 되돌릴 수 없습니다.
              </span>
            }
            okText="삭제"
            okType="danger"
            cancelText="취소"
            onConfirm={() => handleDelete(record)}
          >
            <Tooltip title="삭제">
              <Button
                type="link"
                size="small"
                danger
                icon={<DeleteOutlined />}
              />
            </Tooltip>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 1480 }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          텔레그램 페르소나 관리
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          신사업유통 모듈의 텔레그램 다계정을 등록하고 SMS 2단계 인증으로
          로그인합니다. api_id / api_hash 는 my.telegram.org 에서 발급받습니다.
        </Paragraph>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="전체" value={stats.total} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="로그인됨"
              value={stats.loggedIn}
              valueStyle={{ color: "#3f8600" }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="자격증명만"
              value={stats.credOnly}
              valueStyle={{ color: "#d48806" }}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="미설정"
              value={stats.unset}
              valueStyle={{ color: "#999" }}
            />
          </Card>
        </Col>
      </Row>

      <div
        style={{
          display: "flex",
          justifyContent: "flex-end",
          marginBottom: 16,
        }}
      >
        <Space>
          <Button
            icon={<ReloadOutlined />}
            onClick={() => {
              void fetchData();
            }}
          >
            새로고침
          </Button>
          {isAdmin && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => setCreateOpen(true)}
            >
              새 페르소나 등록
            </Button>
          )}
        </Space>
      </div>

      <Table
        columns={isAdmin ? columns : columns.filter((c) => c.key !== "actions")}
        dataSource={data}
        rowKey="id"
        loading={loading}
        size="middle"
        scroll={{ x: 1280 }}
        pagination={{
          pageSize: 20,
          showSizeChanger: true,
          pageSizeOptions: [10, 20, 50, 100],
          showTotal: (t) => `총 ${t}건`,
        }}
      />

      <PersonaCreateModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          void handleCreated();
        }}
      />

      <PersonaLoginModal
        open={loginTarget !== null}
        persona={loginTarget}
        onClose={() => setLoginTarget(null)}
        onSuccess={() => {
          void handleLoginSuccess();
        }}
      />

      <PersonaCredentialsModal
        open={credsTarget !== null}
        persona={credsTarget}
        onClose={() => setCredsTarget(null)}
        onUpdated={() => {
          void fetchData();
        }}
      />

      <PersonaBusinessNameModal
        open={nameEditTarget !== null}
        persona={nameEditTarget}
        onClose={() => setNameEditTarget(null)}
        onUpdated={() => {
          void fetchData();
        }}
      />
    </div>
  );
}

