import { useEffect, useState } from "react";
import {
  Card,
  DatePicker,
  Segmented,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import {
  getDocumentsUsage,
  type UsageGroupBy,
  type UsageKindFilter,
  type UsageResponse,
  type UsageRow,
} from "../../api/documentsAdmin";

const { Title, Paragraph } = Typography;
const { RangePicker } = DatePicker;

const KIND_COLOR: Record<string, string> = {
  fill: "blue",
  generate: "purple",
};

const KIND_LABEL: Record<UsageGroupBy, string> = {
  day: "일별",
  user: "사용자별",
  kind: "종류별",
};

const BUCKET_HEADER: Record<UsageGroupBy, string> = {
  day: "날짜",
  user: "사용자",
  kind: "종류",
};

export default function DocumentsUsagePage() {
  const [report, setReport] = useState<UsageResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [groupBy, setGroupBy] = useState<UsageGroupBy>("day");
  const [kind, setKind] = useState<UsageKindFilter>("all");
  const [range, setRange] = useState<[string | null, string | null]>([
    null,
    null,
  ]);

  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      setLoading(true);
      try {
        const data = await getDocumentsUsage({
          start: range[0] ?? undefined,
          end: range[1] ?? undefined,
          group_by: groupBy,
          kind,
        });
        if (!cancelled) setReport(data);
      } catch {
        if (!cancelled) message.error("사용량 조회 실패 (관리자 권한 필요)");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, [groupBy, kind, range]);

  const columns: ColumnsType<UsageRow> = [
    {
      title: BUCKET_HEADER[groupBy],
      dataIndex: "bucket",
      render: (v: string, row: UsageRow) =>
        groupBy === "kind" || row.kind ? (
          <Tag color={KIND_COLOR[v] ?? "default"}>{v}</Tag>
        ) : (
          <Typography.Text>{v}</Typography.Text>
        ),
    },
    {
      title: "잡 수",
      dataIndex: "job_count",
      width: 100,
      align: "right",
      sorter: (a, b) => a.job_count - b.job_count,
    },
    {
      title: "Input 토큰",
      dataIndex: "tokens_in",
      width: 140,
      align: "right",
      render: (v: number) => v.toLocaleString(),
      sorter: (a, b) => a.tokens_in - b.tokens_in,
    },
    {
      title: "Output 토큰",
      dataIndex: "tokens_out",
      width: 140,
      align: "right",
      render: (v: number) => v.toLocaleString(),
      sorter: (a, b) => a.tokens_out - b.tokens_out,
    },
    {
      title: "비용 (USD)",
      dataIndex: "cost_usd",
      width: 140,
      align: "right",
      render: (v: number) => `$${Number(v).toFixed(4)}`,
      sorter: (a, b) => a.cost_usd - b.cost_usd,
      defaultSortOrder: "descend",
    },
  ];

  return (
    <div style={{ maxWidth: 1200 }}>
      <div style={{ marginBottom: 16 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          문서 사용량 (토큰/비용)
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          양식 작성·문서 생성 잡의 토큰·비용 집계 — 관리자 전용. 기본 최근 30일.
        </Paragraph>
      </div>

      <Space direction="vertical" size={16} style={{ width: "100%" }}>
        <Card size="small" title="합계">
          <Space size="large" wrap align="center">
            <Statistic
              title="총 비용 (USD)"
              value={report ? Number(report.totals.cost_usd) : 0}
              precision={4}
              prefix="$"
              loading={loading}
            />
            <Statistic
              title="총 잡 수"
              value={report?.totals.job_count ?? 0}
              loading={loading}
            />
            <Statistic
              title="Input 토큰"
              value={report?.totals.tokens_in ?? 0}
              loading={loading}
            />
            <Statistic
              title="Output 토큰"
              value={report?.totals.tokens_out ?? 0}
              loading={loading}
            />
          </Space>
        </Card>

        <Card size="small">
          <Space size="middle" wrap align="center">
            <Segmented
              value={groupBy}
              onChange={(v) => setGroupBy(v as UsageGroupBy)}
              options={(["day", "user", "kind"] as UsageGroupBy[]).map((g) => ({
                label: KIND_LABEL[g],
                value: g,
              }))}
            />
            <Segmented
              value={kind}
              onChange={(v) => setKind(v as UsageKindFilter)}
              options={[
                { label: "전체", value: "all" },
                { label: "양식 작성", value: "fill" },
                { label: "문서 생성", value: "generate" },
              ]}
            />
            <RangePicker
              onChange={(_dates, strings) =>
                setRange([strings[0] || null, strings[1] || null])
              }
              placeholder={["시작일", "종료일"]}
              presets={[
                {
                  label: "최근 7일",
                  value: [dayjs().subtract(6, "day"), dayjs()],
                },
                {
                  label: "최근 30일",
                  value: [dayjs().subtract(29, "day"), dayjs()],
                },
              ]}
            />
          </Space>
        </Card>

        <Card size="small" title={`${KIND_LABEL[groupBy]} 집계`}>
          <Table
            size="small"
            rowKey={(r) => `${r.bucket}-${r.kind ?? ""}`}
            columns={columns}
            dataSource={report?.rows ?? []}
            loading={loading}
            pagination={{ pageSize: 31, showSizeChanger: false }}
          />
        </Card>
      </Space>
    </div>
  );
}
