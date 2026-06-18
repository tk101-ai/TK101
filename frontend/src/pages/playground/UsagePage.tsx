import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  DatePicker,
  Form,
  InputNumber,
  Modal,
  Progress,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
  Space,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { EditOutlined } from "@ant-design/icons";
import {
  adminGetUserQuotas,
  adminUpdateUserQuota,
  getAdminUsage,
  getMyQuota,
  type PlaygroundAdminUserQuota,
  type PlaygroundQuotaInfo,
  type PlaygroundUsageByModel,
  type PlaygroundUsageByUser,
  type PlaygroundUsageReport,
} from "../../api/playground";

const { Title, Paragraph } = Typography;
const { RangePicker } = DatePicker;

const KIND_COLOR: Record<string, string> = {
  text: "blue",
  image: "magenta",
  video: "purple",
};

function num(v: number | string | null | undefined): number {
  if (v === null || v === undefined) return 0;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

export default function UsagePage() {
  const [report, setReport] = useState<PlaygroundUsageReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState<[string | null, string | null]>([null, null]);

  // 본인 이번 달 한도/사용량/잔여 (모든 사용자 공통 — /me/quota).
  const [myQuota, setMyQuota] = useState<PlaygroundQuotaInfo | null>(null);
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const data = await getMyQuota();
        if (!cancelled) setMyQuota(data);
      } catch {
        if (!cancelled) setMyQuota(null);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      try {
        const data = await getAdminUsage(range[0] ?? undefined, range[1] ?? undefined);
        if (!cancelled) setReport(data);
      } catch {
        if (!cancelled) message.error("사용량 조회 실패 (admin 권한 필요)");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [range]);

  // 사용자 한도 관리.
  const [quotas, setQuotas] = useState<PlaygroundAdminUserQuota[]>([]);
  const [quotasLoading, setQuotasLoading] = useState(false);
  const [editTarget, setEditTarget] = useState<PlaygroundAdminUserQuota | null>(
    null,
  );
  const [quotaForm] = Form.useForm<{ monthly_quota_usd: number }>();
  const [editSaving, setEditSaving] = useState(false);

  const fetchQuotas = useCallback(async () => {
    setQuotasLoading(true);
    try {
      const data = await adminGetUserQuotas();
      setQuotas(data);
    } catch {
      message.error("사용자 한도 조회 실패");
    } finally {
      setQuotasLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchQuotas();
  }, [fetchQuotas]);

  const openEditQuota = (q: PlaygroundAdminUserQuota) => {
    setEditTarget(q);
    quotaForm.setFieldsValue({
      monthly_quota_usd: Number(q.monthly_quota_usd),
    });
  };

  const submitEditQuota = async () => {
    if (!editTarget) return;
    try {
      const values = await quotaForm.validateFields();
      setEditSaving(true);
      await adminUpdateUserQuota(editTarget.user_id, values.monthly_quota_usd);
      message.success(`${editTarget.user_email} 한도가 변경되었습니다`);
      setEditTarget(null);
      void fetchQuotas();
    } catch (err: unknown) {
      if ((err as { errorFields?: unknown }).errorFields) {
        return;
      }
      message.error("한도 수정 실패");
    } finally {
      setEditSaving(false);
    }
  };

  const quotaCols: ColumnsType<PlaygroundAdminUserQuota> = [
    {
      title: "사용자",
      dataIndex: "user_email",
      render: (v: string) => <Typography.Text style={{ fontSize: 12 }}>{v}</Typography.Text>,
    },
    {
      title: "월 한도 (USD)",
      dataIndex: "monthly_quota_usd",
      width: 140,
      align: "right",
      render: (v: number | string) => `$${Number(v).toFixed(2)}`,
      sorter: (a, b) =>
        Number(a.monthly_quota_usd) - Number(b.monthly_quota_usd),
    },
    {
      title: "이번 달 사용",
      dataIndex: "current_usage_usd",
      width: 140,
      align: "right",
      render: (v: number | string) => `$${Number(v).toFixed(4)}`,
      sorter: (a, b) =>
        Number(a.current_usage_usd) - Number(b.current_usage_usd),
    },
    {
      title: "남은 한도",
      dataIndex: "remaining_usd",
      width: 140,
      align: "right",
      render: (v: number | string) => {
        const n = Number(v);
        return (
          <Typography.Text style={{ color: n <= 0 ? "#ff4d4f" : undefined }}>
            ${n.toFixed(4)}
          </Typography.Text>
        );
      },
    },
    {
      title: "작업",
      key: "actions",
      width: 110,
      render: (_, record) => (
        <Button
          size="small"
          icon={<EditOutlined />}
          onClick={() => openEditQuota(record)}
        >
          한도 수정
        </Button>
      ),
    },
  ];

  const modelCols: ColumnsType<PlaygroundUsageByModel> = [
    {
      title: "유형",
      dataIndex: "kind",
      width: 80,
      render: (k: string) => <Tag color={KIND_COLOR[k] ?? "default"}>{k}</Tag>,
    },
    {
      title: "모델",
      dataIndex: "model",
      render: (m: string) => <code style={{ fontSize: 12 }}>{m}</code>,
    },
    { title: "호출 수", dataIndex: "request_count", width: 100, align: "right" },
    {
      title: "Input 토큰",
      dataIndex: "input_tokens",
      width: 120,
      align: "right",
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: "Output 토큰",
      dataIndex: "output_tokens",
      width: 120,
      align: "right",
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: "비용 (USD)",
      dataIndex: "cost_usd",
      width: 120,
      align: "right",
      render: (v: number) => `$${Number(v).toFixed(4)}`,
      sorter: (a, b) => Number(a.cost_usd) - Number(b.cost_usd),
      defaultSortOrder: "descend",
    },
  ];

  const userCols: ColumnsType<PlaygroundUsageByUser> = [
    { title: "사용자", dataIndex: "user_email" },
    { title: "호출 수", dataIndex: "request_count", width: 100, align: "right" },
    {
      title: "Input",
      dataIndex: "input_tokens",
      width: 120,
      align: "right",
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: "Output",
      dataIndex: "output_tokens",
      width: 120,
      align: "right",
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: "비용 (USD)",
      dataIndex: "cost_usd",
      width: 120,
      align: "right",
      render: (v: number) => `$${Number(v).toFixed(4)}`,
      sorter: (a, b) => Number(a.cost_usd) - Number(b.cost_usd),
      defaultSortOrder: "descend",
    },
  ];

  return (
    <div style={{ maxWidth: 1400 }}>
      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          Playground 사용량
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          모델별·사용자별 토큰·비용 — 텐센트 단가표 (2026-05-19) 기준
        </Paragraph>
      </div>

      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        {myQuota ? (
          <Card size="small" title="내 사용량 (이번 달)">
            <Space size="large" wrap align="center">
              <Statistic
                title="월 한도"
                value={num(myQuota.monthly_quota_usd)}
                precision={2}
                prefix="$"
              />
              <Statistic
                title="사용"
                value={num(myQuota.current_usage_usd)}
                precision={4}
                prefix="$"
              />
              <Statistic
                title="잔여"
                value={num(myQuota.remaining_usd)}
                precision={4}
                prefix="$"
                valueStyle={{
                  color:
                    num(myQuota.remaining_usd) <= 0 ? "#ff4d4f" : undefined,
                }}
              />
              <div style={{ minWidth: 200 }}>
                <Progress
                  percent={
                    num(myQuota.monthly_quota_usd) > 0
                      ? Math.min(
                          100,
                          Math.round(
                            (num(myQuota.current_usage_usd) /
                              num(myQuota.monthly_quota_usd)) *
                              100,
                          ),
                        )
                      : 0
                  }
                  status={
                    num(myQuota.remaining_usd) <= 0 ? "exception" : "normal"
                  }
                />
                <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                  {myQuota.period_start?.slice(0, 10)} ~{" "}
                  {myQuota.period_end?.slice(0, 10)}
                </Typography.Text>
              </div>
            </Space>
          </Card>
        ) : null}

        <Card size="small" title="전체 사용량 (admin)">
          <Space size="large" wrap>
            <Statistic
              title="총 비용 (USD)"
              value={report ? Number(report.total_cost_usd) : 0}
              precision={4}
              prefix="$"
              loading={loading}
            />
            <Statistic
              title="총 호출 수"
              value={report?.total_requests ?? 0}
              loading={loading}
            />
            <RangePicker
              showTime
              onChange={(_dates, strings) =>
                setRange([strings[0] || null, strings[1] || null])
              }
              placeholder={["시작", "종료"]}
            />
          </Space>
        </Card>

        <Card title="모델별" size="small">
          <Table
            size="small"
            rowKey={(r) => `${r.kind}-${r.model}`}
            columns={modelCols}
            dataSource={report?.by_model ?? []}
            loading={loading}
            pagination={{ pageSize: 20, showSizeChanger: false }}
          />
        </Card>

        <Card title="사용자별" size="small">
          <Table
            size="small"
            rowKey={(r) => r.user_id}
            columns={userCols}
            dataSource={report?.by_user ?? []}
            loading={loading}
            pagination={{ pageSize: 20, showSizeChanger: false }}
          />
        </Card>

        <Card title="사용자 한도 관리" size="small">
          <Table
            size="small"
            rowKey={(r) => r.user_id}
            columns={quotaCols}
            dataSource={quotas}
            loading={quotasLoading}
            pagination={{ pageSize: 20, showSizeChanger: false }}
          />
        </Card>
      </Space>

      <Modal
        title={editTarget ? `한도 수정 — ${editTarget.user_email}` : "한도 수정"}
        open={editTarget !== null}
        onCancel={() => setEditTarget(null)}
        onOk={() => void submitEditQuota()}
        confirmLoading={editSaving}
        okText="저장"
        cancelText="취소"
        destroyOnClose
      >
        <Form form={quotaForm} layout="vertical" preserve={false}>
          <Form.Item
            name="monthly_quota_usd"
            label="월 한도 (USD)"
            rules={[
              { required: true, message: "한도를 입력하세요" },
              {
                type: "number",
                min: 0,
                message: "0 이상의 값이어야 합니다",
              },
            ]}
          >
            <InputNumber
              min={0}
              step={1}
              precision={2}
              prefix="$"
              style={{ width: "100%" }}
              autoFocus
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
