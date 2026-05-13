import { Card, Table, Segmented, Empty, Alert } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useNavigate } from "react-router-dom";
import type { TopCounterpartRow } from "../../api/transactions";

/**
 * 상위 거래처 Top 5 (재무 대시보드 — Wave 3 FE-C).
 *
 * - 지출 기준 (출금 합계)
 * - 거래처 행 클릭 → /transactions?keyword={name}
 * - 기간 토글: 이번 분기 / 이번 달 / 작년 동기
 */

export type PeriodKey = "this_quarter" | "this_month" | "last_year_same";

interface TopCounterpartsTableProps {
  data: TopCounterpartRow[];
  period: PeriodKey;
  onPeriodChange: (period: PeriodKey) => void;
  loading?: boolean;
  error?: string | null;
}

const PERIOD_OPTIONS = [
  { label: "이번 분기", value: "this_quarter" as const },
  { label: "이번 달", value: "this_month" as const },
  { label: "작년 동기", value: "last_year_same" as const },
];

export default function TopCounterpartsTable({
  data,
  period,
  onPeriodChange,
  loading,
  error,
}: TopCounterpartsTableProps) {
  const navigate = useNavigate();

  const columns: ColumnsType<TopCounterpartRow> = [
    {
      title: "거래처",
      dataIndex: "counterpart_name",
      key: "name",
      render: (val: string | null) => (
        <span style={{ fontWeight: val ? 500 : 400, color: val ? undefined : "rgba(0,0,0,0.45)" }}>
          {val ?? "(미분류)"}
        </span>
      ),
    },
    {
      title: "금액",
      dataIndex: "total_amount",
      key: "amount",
      align: "right",
      width: 140,
      render: (val: string) => (
        <span
          style={{
            color: "#cf1322",
            fontWeight: 600,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {Number(val).toLocaleString("ko-KR")}원
        </span>
      ),
    },
    {
      title: "건수",
      dataIndex: "count",
      key: "count",
      align: "right",
      width: 70,
      render: (val: number) => (
        <span style={{ color: "rgba(0,0,0,0.65)" }}>{val}</span>
      ),
    },
  ];

  return (
    <Card
      title="상위 지출 거래처 Top 5"
      loading={loading}
      extra={
        <Segmented
          options={PERIOD_OPTIONS}
          value={period}
          onChange={(v) => onPeriodChange(v as PeriodKey)}
          size="small"
        />
      }
    >
      {error ? (
        <Alert
          type="error"
          message="거래처 집계 조회 실패"
          description={error}
          showIcon
        />
      ) : data.length === 0 ? (
        <Empty description="해당 기간 지출이 없습니다." />
      ) : (
        <Table<TopCounterpartRow>
          columns={columns}
          dataSource={data}
          rowKey={(row) =>
            row.counterpart_id ??
            row.counterpart_name ??
            `__unmatched_${row.total_amount}_${row.count}`
          }
          pagination={false}
          size="small"
          onRow={(row) => ({
            onClick: () => {
              if (row.counterpart_name) {
                navigate(
                  `/transactions?keyword=${encodeURIComponent(row.counterpart_name)}`,
                );
              }
            },
            style: { cursor: row.counterpart_name ? "pointer" : "default" },
          })}
        />
      )}
    </Card>
  );
}
