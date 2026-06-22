import { Card, DatePicker, Space, Empty, Alert } from "antd";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import { useMemo } from "react";
import dayjs, { type Dayjs } from "dayjs";
import type { MonthlySummaryRow } from "../../api/transactions";
import { formatKRW } from "../../utils/format";

const { RangePicker } = DatePicker;

/**
 * 월별 입출금 추이 Bar Chart (재무 대시보드 — Wave 3 FE-C).
 *
 * - X축: 월 (YYYY-MM)
 * - Y축: 금액
 * - 입금(녹색), 출금(빨강) 그룹 막대
 * - 호버 시 net 값 표시
 *
 * recharts 라이브러리 채택 이유: 가볍고 React 19 호환, 트리쉐이킹 지원.
 */

interface MonthlyChartProps {
  data: MonthlySummaryRow[];
  range: [Dayjs, Dayjs];
  onRangeChange: (range: [Dayjs, Dayjs]) => void;
  loading?: boolean;
  error?: string | null;
}

interface ChartDatum {
  month: string;
  deposit: number;
  withdrawal: number;
  net: number;
  count: number;
}


interface TooltipPayloadItem {
  name?: string;
  value?: number;
  color?: string;
  payload?: ChartDatum;
}

function CustomTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: TooltipPayloadItem[];
  label?: string;
}) {
  if (!active || !payload || payload.length === 0) return null;
  const datum = payload[0]?.payload;
  if (!datum) return null;
  return (
    <div
      style={{
        background: "#fff",
        padding: "10px 14px",
        border: "1px solid #f0f0f0",
        borderRadius: 6,
        boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
        fontSize: 12,
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{label}</div>
      <div style={{ color: "#52c41a" }}>
        입금: {datum.deposit.toLocaleString("ko-KR")}원
      </div>
      <div style={{ color: "#cf1322" }}>
        출금: {datum.withdrawal.toLocaleString("ko-KR")}원
      </div>
      <div
        style={{
          marginTop: 4,
          paddingTop: 4,
          borderTop: "1px dashed #f0f0f0",
          color: datum.net >= 0 ? "#1677ff" : "#cf1322",
          fontWeight: 600,
        }}
      >
        순증감: {datum.net >= 0 ? "+" : ""}
        {datum.net.toLocaleString("ko-KR")}원
      </div>
      <div style={{ color: "rgba(0,0,0,0.45)", marginTop: 2 }}>
        {datum.count}건
      </div>
    </div>
  );
}

export default function MonthlyChart({
  data,
  range,
  onRangeChange,
  loading,
  error,
}: MonthlyChartProps) {
  const chartData = useMemo<ChartDatum[]>(() => {
    return data.map((row) => ({
      month: row.month,
      deposit: Number(row.deposit_total) || 0,
      withdrawal: Number(row.withdrawal_total) || 0,
      net: Number(row.net) || 0,
      count: row.count,
    }));
  }, [data]);

  const handleRangeChange = (value: unknown) => {
    if (Array.isArray(value) && value[0] && value[1]) {
      onRangeChange([value[0] as Dayjs, value[1] as Dayjs]);
    }
  };

  return (
    <Card
      title="월별 입출금 추이"
      loading={loading}
      extra={
        <Space>
          <RangePicker
            picker="month"
            value={range}
            onChange={handleRangeChange}
            allowClear={false}
            disabledDate={(d) => d && d.isAfter(dayjs().endOf("month"))}
          />
        </Space>
      }
    >
      {error ? (
        <Alert
          type="error"
          message="월별 집계 조회 실패"
          description={error}
          showIcon
        />
      ) : chartData.length === 0 ? (
        <Empty description="해당 기간 거래내역이 없습니다." />
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <BarChart
            data={chartData}
            margin={{ top: 8, right: 16, left: 8, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="month"
              tick={{ fontSize: 12 }}
              stroke="rgba(0,0,0,0.45)"
            />
            <YAxis
              tick={{ fontSize: 12 }}
              stroke="rgba(0,0,0,0.45)"
              tickFormatter={formatKRW}
            />
            <Tooltip content={<CustomTooltip />} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar
              dataKey="deposit"
              name="입금"
              fill="#52c41a"
              radius={[4, 4, 0, 0]}
            />
            <Bar
              dataKey="withdrawal"
              name="출금"
              fill="#cf1322"
              radius={[4, 4, 0, 0]}
            />
          </BarChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}
