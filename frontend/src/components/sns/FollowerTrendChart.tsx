import { useMemo } from "react";
import { Empty } from "antd";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getLanguageLabel,
  getPlatformLabel,
  type TrendPoint,
} from "../../api/sns";

// 채널 시리즈 색상 팔레트 (PostMetricsDrawer 색감과 일관).
const SERIES_COLORS = [
  "#1677ff",
  "#13c2c2",
  "#fa8c16",
  "#722ed1",
  "#52c41a",
  "#eb2f96",
  "#faad14",
  "#2f54eb",
];

interface FollowerTrendChartProps {
  data: TrendPoint[];
  height?: number;
}

interface SeriesMeta {
  key: string; // account_id
  name: string; // 라벨 (플랫폼·어권·핸들)
}

/**
 * 팔로워 추이 멀티라인 차트.
 *
 * `GET /api/sns/stats/trend` 응답(TrendPoint[])을 period(X축) × 채널(시리즈)로 피벗해 렌더한다.
 * 채널 추가/삭제는 입력 데이터에 따라 자동 반영(하드코딩 없음).
 */
export default function FollowerTrendChart({ data, height = 320 }: FollowerTrendChartProps) {
  const { rows, series } = useMemo(() => {
    const seriesMap = new Map<string, SeriesMeta>();
    const periodMap = new Map<string, Record<string, number | string>>();

    for (const point of data) {
      if (!seriesMap.has(point.account_id)) {
        const handle = point.handle ?? point.account_id.slice(0, 8);
        seriesMap.set(point.account_id, {
          key: point.account_id,
          name: `${getPlatformLabel(point.platform)}·${getLanguageLabel(point.language)} ${handle}`,
        });
      }
      const row = periodMap.get(point.period) ?? { period: point.period };
      row[point.account_id] = point.followers;
      periodMap.set(point.period, row);
    }

    // period 라벨은 "YYYY-MM-Wn" 형태라 사전순 정렬이 곧 시간순.
    const sortedRows = Array.from(periodMap.values()).sort((a, b) =>
      String(a.period).localeCompare(String(b.period)),
    );
    return { rows: sortedRows, series: Array.from(seriesMap.values()) };
  }, [data]);

  if (series.length === 0) {
    return <Empty description="팔로워 스냅샷 데이터가 없습니다" />;
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={rows} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
        <XAxis dataKey="period" tick={{ fontSize: 12 }} stroke="rgba(0,0,0,0.45)" />
        <YAxis
          tick={{ fontSize: 12 }}
          stroke="rgba(0,0,0,0.45)"
          tickFormatter={(v: number) => v.toLocaleString("ko-KR")}
          width={64}
        />
        <Tooltip formatter={(v) => Number(v).toLocaleString("ko-KR")} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        {series.map((s, idx) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.name}
            stroke={SERIES_COLORS[idx % SERIES_COLORS.length]}
            dot={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
