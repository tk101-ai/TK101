import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Card, Segmented, Space, Spin, Statistic, Tag, Typography } from "antd";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  getAigcMonitor,
  type AigcMonitorReport,
} from "../../api/playground";

const { Title, Text, Paragraph } = Typography;

const TYPE_LABEL: Record<string, string> = {
  Text: "텍스트(LLM)",
  Image: "이미지",
  Video: "영상",
};
const TYPE_COLOR: Record<string, string> = {
  Text: "#2F6FED",
  Image: "#C2185B",
  Video: "#7B1FA2",
};

/** 텐센트 AIGC 게이트웨이 사용량·Quota 모니터(관리자). DescribeAigcUsageData/Quotas 기반. */
export default function AigcMonitorSection() {
  const [days, setDays] = useState(14);
  const [data, setData] = useState<AigcMonitorReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const load = useCallback(async (d: number) => {
    setLoading(true);
    setErr(null);
    try {
      setData(await getAigcMonitor(d));
    } catch (e: unknown) {
      setErr(
        (e as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "AIGC 모니터 조회 실패",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(days);
  }, [days, load]);

  // 일별 통합 차트 데이터: {date, Text, Image, Video} (count 기준)
  const chart = useMemo(() => {
    if (!data) return [];
    const byDate: Record<string, Record<string, number>> = {};
    for (const t of Object.keys(data.types)) {
      for (const row of data.types[t].usage) {
        byDate[row.date] = byDate[row.date] || { date: row.date };
        byDate[row.date][t] = row.count;
      }
    }
    return Object.values(byDate).sort((a, b) =>
      String(a.date).localeCompare(String(b.date)),
    );
  }, [data]);

  return (
    <Card
      style={{ marginBottom: 20 }}
      title={
        <Space size={8} wrap>
          <Title level={5} style={{ margin: 0 }}>
            텐센트 AIGC 게이트웨이 사용량·한도
          </Title>
          <Tag color="purple" bordered={false}>
            SubAppId {data?.subapp_id || "-"}
          </Tag>
        </Space>
      }
      extra={
        <Segmented
          value={days}
          onChange={(v) => setDays(Number(v))}
          options={[
            { label: "7일", value: 7 },
            { label: "14일", value: 14 },
            { label: "30일", value: 30 },
          ]}
        />
      }
    >
      <Paragraph type="secondary" style={{ marginTop: 0 }}>
        텐센트 측 집계(DescribeAigcUsageData)와 한도(DescribeAigcQuotas) 직접 조회. 내부 DB
        사용량/비용은 아래 표 참조.
      </Paragraph>

      {err && <Alert type="warning" showIcon message={err} style={{ marginBottom: 12 }} />}

      <Spin spinning={loading}>
        <Space size={24} wrap style={{ marginBottom: 16 }}>
          {data &&
            Object.entries(data.types).map(([t, d]) => (
              <div key={t} style={{ minWidth: 180 }}>
                <Space size={6}>
                  <Tag color={TYPE_COLOR[t]} bordered={false}>
                    {TYPE_LABEL[t] ?? t}
                  </Tag>
                  {d.quotas.length === 0 ? (
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      한도 미설정(기본)
                    </Text>
                  ) : (
                    <Tag color="gold" bordered={false}>
                      한도 {d.quotas.length}건
                    </Tag>
                  )}
                </Space>
                <div style={{ display: "flex", gap: 18, marginTop: 4 }}>
                  <Statistic title="호출 수" value={d.total_count} />
                  <Statistic title="사용량(토큰)" value={d.total_usage} />
                </div>
              </div>
            ))}
        </Space>

        <div style={{ width: "100%", height: 260 }}>
          <ResponsiveContainer>
            <BarChart data={chart} margin={{ top: 4, right: 8, left: 0, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Legend />
              <Bar dataKey="Text" name="텍스트" fill={TYPE_COLOR.Text} stackId="a" />
              <Bar dataKey="Image" name="이미지" fill={TYPE_COLOR.Image} stackId="a" />
              <Bar dataKey="Video" name="영상" fill={TYPE_COLOR.Video} stackId="a" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Spin>
    </Card>
  );
}
