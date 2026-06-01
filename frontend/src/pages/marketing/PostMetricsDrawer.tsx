import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Drawer,
  Empty,
  List,
  Segmented,
  Space,
  Spin,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import { LikeOutlined } from "@ant-design/icons";
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
  listPostComments,
  listPostMetrics,
  type MetricSnapshot,
  type SnsComment,
  type SnsPost,
} from "../../api/sns";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Title, Text, Paragraph } = Typography;

type Period = "daily" | "weekly";
type TabKey = "metrics" | "comments";

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
 * 게시물별 메트릭 시계열 + 댓글 본문 Drawer.
 *
 * - 메트릭 탭: social_post_metric_snapshots(022)를 일/주 주기로 라인 차트.
 * - 댓글 탭: social_post_comments(026)를 오래된→최신 순으로 목록 표시.
 * 데이터가 없으면(토큰 미설정/미수집) 안내 문구만 노출.
 */
export default function PostMetricsDrawer({ post, onClose }: PostMetricsDrawerProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("metrics");
  const [period, setPeriod] = useState<Period>("daily");
  const [snapshots, setSnapshots] = useState<MetricSnapshot[]>([]);
  const [loading, setLoading] = useState(false);
  const [comments, setComments] = useState<SnsComment[]>([]);
  const [commentsLoading, setCommentsLoading] = useState(false);

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

  const fetchComments = useCallback(async () => {
    if (!post) return;
    setCommentsLoading(true);
    try {
      const res = await listPostComments(post.id);
      setComments(res.data);
    } catch (err) {
      message.error(extractErrorDetail(err, "댓글 조회 실패"));
    } finally {
      setCommentsLoading(false);
    }
  }, [post]);

  useEffect(() => {
    if (post) void fetchMetrics();
    else setSnapshots([]);
  }, [post, fetchMetrics]);

  // 댓글은 댓글 탭이 열렸을 때만 조회 (불필요한 호출 회피).
  useEffect(() => {
    if (post && activeTab === "comments") void fetchComments();
    else if (!post) setComments([]);
  }, [post, activeTab, fetchComments]);

  const chartData = useMemo(() => snapshots.map(toChartDatum), [snapshots]);

  const metricsTab = (
    <>
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
        <Segmented
          value={period}
          onChange={(v) => setPeriod(v as Period)}
          options={[
            { value: "daily", label: "일간" },
            { value: "weekly", label: "주간" },
          ]}
        />
      </div>
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
    </>
  );

  const commentsTab = (
    <Spin spinning={commentsLoading}>
      {comments.length === 0 ? (
        <Empty
          description={
            <Space direction="vertical" size={4}>
              <span>수집된 댓글이 없습니다</span>
              <Text type="secondary" style={{ fontSize: 12 }}>
                메타 API 토큰 등록 후 '댓글 수집'을 실행하면 본문이 저장됩니다.
                (소유/관리 계정 게시물만 가능)
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
            style={{ marginBottom: 12 }}
            message={`댓글 ${comments.length}개`}
          />
          <List
            dataSource={comments}
            size="small"
            renderItem={(c) => (
              <List.Item>
                <List.Item.Meta
                  title={
                    <Space size={8} wrap>
                      <Text strong>{c.author || "(작성자 미상)"}</Text>
                      {c.commented_at ? (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          {c.commented_at.slice(0, 16).replace("T", " ")}
                        </Text>
                      ) : null}
                      {c.like_count != null ? (
                        <Tag icon={<LikeOutlined />} color="default" style={{ marginInlineEnd: 0 }}>
                          {c.like_count}
                        </Tag>
                      ) : null}
                    </Space>
                  }
                  description={
                    <Paragraph style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                      {c.text || "(내용 없음)"}
                    </Paragraph>
                  }
                />
              </List.Item>
            )}
          />
        </>
      )}
    </Spin>
  );

  return (
    <Drawer
      open={post != null}
      onClose={onClose}
      width={640}
      title={
        <Space direction="vertical" size={0}>
          <Title level={5} style={{ margin: 0 }}>
            게시물 상세
          </Title>
          <Text type="secondary" ellipsis style={{ maxWidth: 520 }}>
            {post?.title || "(제목 없음)"}
          </Text>
        </Space>
      }
    >
      <Tabs
        activeKey={activeTab}
        onChange={(k) => setActiveTab(k as TabKey)}
        items={[
          { key: "metrics", label: "메트릭 추이", children: metricsTab },
          { key: "comments", label: "댓글", children: commentsTab },
        ]}
      />
    </Drawer>
  );
}
