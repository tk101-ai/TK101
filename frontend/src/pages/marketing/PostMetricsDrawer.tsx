import { useCallback, useEffect, useMemo, useState } from "react";
import { Alert, Drawer, Empty, Segmented, Space, Spin, Typography, message } from "antd";
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
import { listPostMetrics, type MetricSnapshot, type SnsPost } from "../../api/sns";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Title, Text } = Typography;

type Period = "daily" | "weekly";

interface PostMetricsDrawerProps {
  post: SnsPost | null;
  onClose: () => void;
}

interface ChartDatum {
  date: string;
  views: number | null;
  reach: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  engagement: number | null;
}

function toChartDatum(snap: MetricSnapshot): ChartDatum {
  return {
    date: snap.captured_at.slice(0, 10),
    views: snap.views,
    reach: snap.reach,
    likes: snap.likes,
    comments: snap.comments,
    shares: snap.shares,
    engagement: snap.engagement_total,
  };
}

/**
 * 게시물별 메트릭 시계열 Drawer.
 *
 * social_post_metric_snapshots(022) 를 일/주 주기로 조회해 라인 차트로 표시.
 * 메트릭이 없으면(토큰 미설정/미수집) 안내 문구만 노출.
 */
export default function PostMetricsDrawer({ post, onClose }: PostMetricsDrawerProps) {
  const [period, setPeriod] = useState<Period>("daily");
  const [snapshots, setSnapshots] = useState<MetricSnapshot[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchMetrics = useCallback(async () => {
    if (!post) return;
    setLoading(true);
    try {
      const res = await listPostMetrics(post.id, period);
      setSnapshots(res.data);
    } catch (err) {
      message.error(extractErrorDetail(err, "메트릭 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [post, period]);

  useEffect(() => {
    if (post) void fetchMetrics();
    else setSnapshots([]);
  }, [post, fetchMetrics]);

  const chartData = useMemo(() => snapshots.map(toChartDatum), [snapshots]);

  return (
    <Drawer
      open={post != null}
      onClose={onClose}
      width={640}
      title={
        <Space direction="vertical" size={0}>
          <Title level={5} style={{ margin: 0 }}>
            메트릭 추이
          </Title>
          <Text type="secondary" ellipsis style={{ maxWidth: 520 }}>
            {post?.title || "(제목 없음)"}
          </Text>
        </Space>
      }
      extra={
        <Segmented
          value={period}
          onChange={(v) => setPeriod(v as Period)}
          options={[
            { value: "daily", label: "일간" },
            { value: "weekly", label: "주간" },
          ]}
        />
      }
    >
      <Spin spinning={loading}>
        {chartData.length === 0 ? (
          <Empty
            description={
              <Space direction="vertical" size={4}>
                <span>수집된 메트릭이 없습니다</span>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  메타 API 토큰 등록 후 '메트릭 수집'을 실행하면 시계열이 쌓입니다.
                </Text>
              </Space>
            }
            style={{ padding: "48px 0" }}
          />
        ) : (
          <>
            <Alert
              type="info"
              showIcon
              banner
              style={{ marginBottom: 16 }}
              message={`스냅샷 ${chartData.length}개 (${period === "daily" ? "일간" : "주간"})`}
            />
            <ResponsiveContainer width="100%" height={340}>
              <LineChart data={chartData} margin={{ top: 8, right: 16, left: 8, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="rgba(0,0,0,0.45)" />
                <YAxis tick={{ fontSize: 12 }} stroke="rgba(0,0,0,0.45)" />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Line type="monotone" dataKey="views" name="조회수" stroke="#1677ff" dot={false} />
                <Line type="monotone" dataKey="reach" name="도달" stroke="#13c2c2" dot={false} />
                <Line type="monotone" dataKey="likes" name="좋아요" stroke="#fa8c16" dot={false} />
                <Line type="monotone" dataKey="comments" name="댓글" stroke="#722ed1" dot={false} />
                <Line type="monotone" dataKey="shares" name="공유" stroke="#52c41a" dot={false} />
                <Line
                  type="monotone"
                  dataKey="engagement"
                  name="합계"
                  stroke="#cf1322"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </>
        )}
      </Spin>
    </Drawer>
  );
}
