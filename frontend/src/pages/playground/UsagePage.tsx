import { useEffect, useState } from "react";
import {
  Card,
  DatePicker,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
  Space,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  getAdminUsage,
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

export default function UsagePage() {
  const [report, setReport] = useState<PlaygroundUsageReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [range, setRange] = useState<[string | null, string | null]>([null, null]);

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
        <Card size="small">
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
              onChange={(dates, strings) =>
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
      </Space>
    </div>
  );
}
