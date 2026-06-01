import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Button,
  Card,
  Popconfirm,
  Radio,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  DeleteOutlined,
  EyeOutlined,
  ReloadOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type { RadioChangeEvent } from "antd";
import dayjs from "dayjs";
import {
  SESSION_STATUS_LABEL,
  SESSION_STATUS_TAG_COLOR,
  deleteSession,
  listSessions,
  type SessionListItem,
  type SessionStatus,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";
import GenerateTriggerModal from "../../components/distribution/GenerateTriggerModal";

const { Title, Paragraph, Text } = Typography;

/**
 * 대화 세션 검수 목록 (T9 Phase C — admin 전용).
 *
 * - 상태 필터: 전체/검수 대기/승인됨/송신 완료/거부됨/실패.
 * - Table: 시나리오, 발신→수신, 상태 배지, 메시지 수, 생성일, 승인일, 비용, 작업.
 * - 상세 페이지 진입은 `/distribution/sessions/:id`.
 */

const PAGE_SIZE = 50;

type StatusFilter = SessionStatus | "all";

const STATUS_FILTER_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "전체" },
  { value: "pending", label: "검수 대기" },
  { value: "approved", label: "승인됨" },
  { value: "scheduled", label: "예약됨" },
  { value: "sent", label: "송신 완료" },
  { value: "rejected", label: "거부됨" },
  { value: "failed", label: "실패" },
];

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dayjs(iso).format("YYYY-MM-DD HH:mm");
}

function formatCost(value: string | null): string {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return `$${n.toFixed(4)}`;
}

export default function SessionsPage() {
  const [data, setData] = useState<SessionListItem[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [page, setPage] = useState<number>(1);
  const [total, setTotal] = useState<number>(0);

  // 생성 트리거 모달 — 페르소나/시나리오/주차 선택 후 POST /generate-custom 호출.
  const [triggerOpen, setTriggerOpen] = useState<boolean>(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const params =
        statusFilter === "all"
          ? { limit: PAGE_SIZE, offset: (page - 1) * PAGE_SIZE }
          : {
              status: statusFilter,
              limit: PAGE_SIZE,
              offset: (page - 1) * PAGE_SIZE,
            };
      const res = await listSessions(params);
      setData(res.items);
      // 백엔드가 total 을 안 줄 수도 있어 length 로 fallback.
      setTotal(typeof res.total === "number" ? res.total : res.items.length);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "세션 목록 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, page]);

  useEffect(() => {
    const run = async () => {
      await fetchData();
    };
    void run();
  }, [fetchData]);

  const handleStatusChange = (event: RadioChangeEvent) => {
    setStatusFilter(event.target.value as StatusFilter);
    setPage(1);
  };

  // 검수 대기 / 거부 / 실패 세션만 삭제 가능 (백엔드와 동일 규칙).
  const handleDelete = useCallback(
    async (id: string) => {
      try {
        await deleteSession(id);
        message.success("세션을 삭제했습니다.");
        await fetchData();
      } catch (err: unknown) {
        message.error(extractErrorDetail(err, "세션 삭제 실패"));
      }
    },
    [fetchData],
  );

  const columns = useMemo<ColumnsType<SessionListItem>>(
    () => [
      {
        title: "시나리오",
        dataIndex: "scenario_name",
        width: 220,
        render: (value: string) => <Text strong>{value}</Text>,
      },
      {
        title: "발신 → 수신",
        key: "route",
        width: 280,
        render: (_: unknown, record: SessionListItem) => (
          <Space size={4} direction="vertical" style={{ lineHeight: 1.4 }}>
            <Text>
              <Text type="secondary" style={{ marginRight: 4 }}>
                발신:
              </Text>
              {record.sender_account_label}
            </Text>
            <Text>
              <Text type="secondary" style={{ marginRight: 4 }}>
                수신:
              </Text>
              {record.receiver_account_label}
            </Text>
          </Space>
        ),
      },
      {
        title: "상태",
        dataIndex: "status",
        width: 110,
        render: (value: SessionStatus) => (
          <Tag color={SESSION_STATUS_TAG_COLOR[value]}>
            {SESSION_STATUS_LABEL[value]}
          </Tag>
        ),
      },
      {
        title: "메시지 수",
        dataIndex: "message_count",
        width: 100,
        align: "right" as const,
        render: (value: number) => (
          <span style={{ fontVariantNumeric: "tabular-nums" }}>{value}</span>
        ),
      },
      {
        title: "생성일",
        dataIndex: "generated_at",
        width: 150,
        render: (value: string) => (
          <Text style={{ fontSize: 12 }}>{formatDateTime(value)}</Text>
        ),
      },
      {
        title: "승인일",
        dataIndex: "approved_at",
        width: 150,
        render: (value: string | null) => (
          <Text type={value ? undefined : "secondary"} style={{ fontSize: 12 }}>
            {formatDateTime(value)}
          </Text>
        ),
      },
      {
        title: "비용 (USD)",
        dataIndex: "llm_cost_usd",
        width: 110,
        align: "right" as const,
        render: (value: string | null) => (
          <span style={{ fontVariantNumeric: "tabular-nums" }}>
            {formatCost(value)}
          </span>
        ),
      },
      {
        title: "작업",
        key: "actions",
        width: 180,
        render: (_: unknown, record: SessionListItem) => {
          const deletable =
            record.status === "pending" ||
            record.status === "rejected" ||
            record.status === "failed";
          return (
            <Space size={0}>
              <Link to={`/distribution/sessions/${record.id}`}>
                <Button type="link" size="small" icon={<EyeOutlined />}>
                  상세 보기
                </Button>
              </Link>
              {deletable ? (
                <Popconfirm
                  title="세션 삭제"
                  description="이 세션과 메시지를 삭제합니다. 되돌릴 수 없습니다."
                  okText="삭제"
                  okButtonProps={{ danger: true }}
                  cancelText="취소"
                  onConfirm={() => handleDelete(record.id)}
                >
                  <Button type="link" size="small" danger icon={<DeleteOutlined />}>
                    삭제
                  </Button>
                </Popconfirm>
              ) : null}
            </Space>
          );
        },
      },
    ],
    [handleDelete],
  );

  return (
    <div style={{ maxWidth: 1480 }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          대화 세션 검수
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          생성된 텔레그램 대화 세션을 검수합니다. 메시지 편집 후 승인하면 워커가
          픽업해 송신합니다.
        </Paragraph>
      </div>

      <Card size="small" style={{ marginBottom: 16 }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 12,
            alignItems: "center",
          }}
        >
          <Radio.Group
            options={STATUS_FILTER_OPTIONS}
            value={statusFilter}
            onChange={handleStatusChange}
            optionType="button"
            buttonStyle="solid"
          />
          <Space>
            <Button
              type="primary"
              icon={<ThunderboltOutlined />}
              onClick={() => setTriggerOpen(true)}
            >
              생성 트리거
            </Button>
            <Button
              icon={<ReloadOutlined />}
              onClick={() => {
                void fetchData();
              }}
            >
              새로고침
            </Button>
          </Space>
        </div>
      </Card>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        size="middle"
        scroll={{ x: 1280 }}
        pagination={{
          current: page,
          pageSize: PAGE_SIZE,
          total,
          showSizeChanger: false,
          showTotal: (t) => `총 ${t}건`,
          onChange: (nextPage) => setPage(nextPage),
        }}
      />

      <GenerateTriggerModal
        open={triggerOpen}
        onClose={() => setTriggerOpen(false)}
        onGenerated={(result) => {
          const created = result.sessions_created.length;
          const skipped = result.skipped.length;
          const errors = result.errors.length;
          if (created > 0) {
            message.success(
              `세션 ${created}건 생성됨 (skip ${skipped}, error ${errors})`,
            );
          } else {
            message.warning(
              `생성된 세션이 없습니다 (skip ${skipped}, error ${errors}).`,
            );
          }
          setPage(1);
          void fetchData();
        }}
      />
    </div>
  );
}
