import {
  Card,
  Col,
  Row,
  Select,
  Statistic,
  Table,
  Tag,
  Button,
  Spin,
  message,
  Space,
  Tooltip,
} from "antd";
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  LinkOutlined,
  ReloadOutlined,
  YoutubeFilled,
  FacebookFilled,
  InstagramFilled,
  TeamOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useState, useCallback } from "react";
import dayjs from "dayjs";
import api from "../../api/client";
import type { ColumnsType } from "antd/es/table";
import { listTrend, refreshAll, type TrendPoint } from "../../api/sns";
import FollowerTrendChart from "../../components/sns/FollowerTrendChart";

// ----- Types -----
interface WeeklyKpiRow {
  language: string;
  platform: string;
  year: number;
  month: number;
  week_number: number;
  followers: number;
  post_count: number;
  view_count: number;
  reaction_count: number;
}

interface GrowthCard {
  language: string;
  platform: string;
  // 채널 식별축 — 브랜드(광고주)·핸들. 백필 전 기존 계정은 client=null.
  handle: string | null;
  client: string | null;
  current_followers: number;
  prev_followers: number;
  growth_rate: number;
}

interface TopPost {
  id: string | number;
  posted_at: string;
  title: string;
  language: string;
  platform: string;
  view_count: number;
  total_engagement: number;
  url: string;
}

interface PivotedRow {
  key: string;
  language: string;
  platform: string;
  // 주차→팔로워. 5주차가 있는 달도 자동 반영(백엔드 week-of-month = ((day-1)//7)+1 → 최대 5).
  weeks: Record<number, number>;
  postCount: number;
  viewCount: number;
  reactionCount: number;
}

// ----- Label Maps -----
const LANGUAGE_LABELS: Record<string, string> = {
  en: "영문",
  zh: "중간체",
  ja: "일문",
};

const PLATFORM_LABELS: Record<string, string> = {
  facebook: "페이스북",
  instagram: "인스타",
  twitter: "트위터(X)",
  youtube: "유튜브",
  weibo: "웨이보",
};

const LANGUAGE_OPTIONS = [
  { value: "all", label: "전체 어권" },
  { value: "en", label: "영문" },
  { value: "zh", label: "중간체" },
  { value: "ja", label: "일문" },
];

const PLATFORM_OPTIONS = [
  { value: "all", label: "전체 플랫폼" },
  { value: "facebook", label: "페이스북" },
  { value: "instagram", label: "인스타" },
  { value: "twitter", label: "트위터(X)" },
  { value: "youtube", label: "유튜브" },
  { value: "weibo", label: "웨이보" },
];

const formatNumber = (value: number | null | undefined): string => {
  if (value === null || value === undefined || Number.isNaN(value)) return "0";
  return Number(value).toLocaleString("ko-KR");
};

const formatPercent = (value: number): string => {
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
};

// 데이터에 등장한 주차 집합을 오름차순으로 도출(5주차 달이면 자동 포함).
function deriveWeekNumbers(rows: WeeklyKpiRow[]): number[] {
  const set = new Set<number>();
  for (const row of rows) {
    if (Number.isFinite(row.week_number)) set.add(row.week_number);
  }
  // 데이터가 없으면 최소 1~4주 컬럼은 유지(빈 표에서도 헤더가 자연스럽게 보이도록).
  if (set.size === 0) return [1, 2, 3, 4];
  return Array.from(set).sort((a, b) => a - b);
}

// Pivot: (language, platform, week_number) → row per (language+platform) with week columns
function pivotWeeklyRows(rows: WeeklyKpiRow[]): PivotedRow[] {
  const grouped = new Map<string, PivotedRow>();
  for (const row of rows) {
    const key = `${row.language}__${row.platform}`;
    const existing = grouped.get(key) ?? {
      key,
      language: row.language,
      platform: row.platform,
      weeks: {},
      postCount: 0,
      viewCount: 0,
      reactionCount: 0,
    };
    const next: PivotedRow = { ...existing, weeks: { ...existing.weeks } };
    next.weeks[row.week_number] = row.followers;
    next.postCount += row.post_count ?? 0;
    next.viewCount += row.view_count ?? 0;
    next.reactionCount += row.reaction_count ?? 0;
    grouped.set(key, next);
  }
  // Stable sort: language order (en, zh, ja), then platform order
  const langOrder = ["en", "zh", "ja"];
  const platformOrder = ["facebook", "instagram", "twitter", "youtube", "weibo"];
  return Array.from(grouped.values()).sort((a, b) => {
    const li = langOrder.indexOf(a.language);
    const lj = langOrder.indexOf(b.language);
    if (li !== lj) return li - lj;
    const pi = platformOrder.indexOf(a.platform);
    const pj = platformOrder.indexOf(b.platform);
    return pi - pj;
  });
}

function buildTotalRow(rows: PivotedRow[], weekNumbers: number[]): PivotedRow {
  return rows.reduce<PivotedRow>(
    (acc, row) => {
      const weeks = { ...acc.weeks };
      for (const w of weekNumbers) {
        weeks[w] = (weeks[w] ?? 0) + (row.weeks[w] ?? 0);
      }
      return {
        ...acc,
        weeks,
        postCount: acc.postCount + row.postCount,
        viewCount: acc.viewCount + row.viewCount,
        reactionCount: acc.reactionCount + row.reactionCount,
      };
    },
    {
      key: "__total__",
      language: "__total__",
      platform: "__total__",
      weeks: {},
      postCount: 0,
      viewCount: 0,
      reactionCount: 0,
    },
  );
}

// Year/month select options
const currentYear = dayjs().year();
const YEAR_OPTIONS = Array.from({ length: 5 }, (_, i) => ({
  value: currentYear - i,
  label: `${currentYear - i}년`,
}));
const MONTH_OPTIONS = Array.from({ length: 12 }, (_, i) => ({
  value: i + 1,
  label: `${i + 1}월`,
}));

// ----- Per-platform aggregation for the unified summary -----
const PLATFORM_ICONS: Record<string, React.ReactNode> = {
  youtube: <YoutubeFilled style={{ color: "#ff0000" }} />,
  facebook: <FacebookFilled style={{ color: "#1877f2" }} />,
  instagram: <InstagramFilled style={{ color: "#d62976" }} />,
};

const PLATFORM_DISPLAY_ORDER = ["youtube", "facebook", "instagram"];

interface PlatformSummary {
  platform: string;
  followers: number; // 최신 스냅샷 합산
  growthRate: number; // 가중 평균 성장률(팔로워 비중)
  postCount: number; // 이번 달 게시물 수
  viewCount: number;
}

// growth(채널별 최신/직전 팔로워) + weekly(게시물 집계)를 platform 단위로 합산.
function aggregateByPlatform(
  growth: GrowthCard[],
  weekly: WeeklyKpiRow[],
): PlatformSummary[] {
  const byPlatform = new Map<string, PlatformSummary>();
  const ensure = (platform: string): PlatformSummary => {
    const existing = byPlatform.get(platform);
    if (existing) return existing;
    const fresh: PlatformSummary = {
      platform,
      followers: 0,
      growthRate: 0,
      postCount: 0,
      viewCount: 0,
    };
    byPlatform.set(platform, fresh);
    return fresh;
  };

  // 팔로워 + 성장률(가중합 누적 → 마지막에 나눔). prev 합으로 가중.
  const prevByPlatform = new Map<string, number>();
  for (const card of growth) {
    const row = ensure(card.platform);
    row.followers += card.current_followers;
    const prev = prevByPlatform.get(card.platform) ?? 0;
    prevByPlatform.set(card.platform, prev + card.prev_followers);
  }
  for (const [platform, prevSum] of prevByPlatform) {
    const row = byPlatform.get(platform);
    if (row && prevSum > 0) {
      row.growthRate = (row.followers - prevSum) / prevSum;
    }
  }

  // 게시물 수 / 조회수 (이번 달, 주차 합산).
  for (const r of weekly) {
    const row = ensure(r.platform);
    row.postCount += r.post_count ?? 0;
    row.viewCount += r.view_count ?? 0;
  }

  return Array.from(byPlatform.values()).sort((a, b) => {
    const ai = PLATFORM_DISPLAY_ORDER.indexOf(a.platform);
    const bi = PLATFORM_DISPLAY_ORDER.indexOf(b.platform);
    return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
  });
}

interface TotalsSummary {
  totalFollowers: number;
  followerGrowthRate: number;
  monthPostCount: number;
  totalViews: number;
  totalReactions: number;
  avgEngagementRate: number; // 반응수 / 조회수
}

function computeTotals(
  platforms: PlatformSummary[],
  weekly: WeeklyKpiRow[],
): TotalsSummary {
  const totalFollowers = platforms.reduce((s, p) => s + p.followers, 0);
  const prevFollowers = platforms.reduce(
    (s, p) => s + (p.growthRate !== 0 ? p.followers / (1 + p.growthRate) : p.followers),
    0,
  );
  const followerGrowthRate =
    prevFollowers > 0 ? (totalFollowers - prevFollowers) / prevFollowers : 0;

  const monthPostCount = weekly.reduce((s, r) => s + (r.post_count ?? 0), 0);
  const totalViews = weekly.reduce((s, r) => s + (r.view_count ?? 0), 0);
  const totalReactions = weekly.reduce((s, r) => s + (r.reaction_count ?? 0), 0);
  const avgEngagementRate = totalViews > 0 ? totalReactions / totalViews : 0;

  return {
    totalFollowers,
    followerGrowthRate,
    monthPostCount,
    totalViews,
    totalReactions,
    avgEngagementRate,
  };
}

export default function Marketing1Dashboard() {
  const [year, setYear] = useState<number>(dayjs().year());
  const [month, setMonth] = useState<number>(dayjs().month() + 1);

  const [weeklyData, setWeeklyData] = useState<WeeklyKpiRow[]>([]);
  const [growthData, setGrowthData] = useState<GrowthCard[]>([]);
  const [topPosts, setTopPosts] = useState<TopPost[]>([]);
  const [trendData, setTrendData] = useState<TrendPoint[]>([]);

  const [topLanguage, setTopLanguage] = useState<string>("all");
  const [topPlatform, setTopPlatform] = useState<string>("all");

  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const topParams: Record<string, string | number> = { limit: 5 };
      if (topLanguage !== "all") topParams.language = topLanguage;
      if (topPlatform !== "all") topParams.platform = topPlatform;

      // 위젯별 독립 fetch: 한 엔드포인트가 실패해도 나머지는 그대로 표시한다
      // (예전엔 Promise.all 이라 trend 한 건 실패가 전체 대시보드를 비웠음).
      const [weeklyR, growthR, topR, trendR] = await Promise.allSettled([
        api.get<WeeklyKpiRow[]>("/api/sns/stats/weekly", {
          params: { year, month },
        }),
        api.get<GrowthCard[]>("/api/sns/stats/growth"),
        api.get<TopPost[]>("/api/sns/stats/top-posts", { params: topParams }),
        listTrend({ months: 6 }),
      ]);
      setWeeklyData(weeklyR.status === "fulfilled" ? (weeklyR.value.data ?? []) : []);
      setGrowthData(growthR.status === "fulfilled" ? (growthR.value.data ?? []) : []);
      setTopPosts(topR.status === "fulfilled" ? (topR.value.data ?? []) : []);
      setTrendData(trendR.status === "fulfilled" ? (trendR.value.data ?? []) : []);

      const failed = [weeklyR, growthR, topR, trendR].filter(
        (r) => r.status === "rejected",
      ).length;
      if (failed > 0) {
        message.warning(`일부 데이터를 불러오지 못했습니다 (${failed}건). 표시된 값만 갱신됨.`);
      }
    } catch {
      message.error("대시보드 데이터를 불러오는데 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, [year, month, topLanguage, topPlatform]);

  useEffect(() => {
    // 필터 변경 시 마케팅 대시보드 재요청 (의도된 패턴).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchData();
  }, [fetchData]);

  // 전체 갱신: 모든 활성 계정 동기 일괄 수집 → 완료 후 대시보드 재요청.
  const handleRefreshAll = useCallback(async () => {
    setRefreshing(true);
    const hide = message.loading("전체 갱신 중… (수 초~수십 초 소요)", 0);
    try {
      const { data } = await refreshAll({ includeMetrics: true });
      hide();
      if (data.failed_count > 0) {
        message.warning(
          `갱신 완료 — 성공 ${data.ok_count}건, 실패 ${data.failed_count}건. ` +
            `실패 계정은 토큰/권한을 확인하세요.`,
        );
      } else {
        message.success(`전체 갱신 완료 — ${data.ok_count}개 계정 갱신됨.`);
      }
      // 부분 실패(메트릭만 실패 등) 사유를 추가로 안내.
      const partial = data.results.filter((r) => r.ok && r.errors.length > 0);
      if (partial.length > 0) {
        message.info(
          `일부 지표 미수집: ${partial
            .map((r) => `${r.platform}/${r.language}`)
            .join(", ")}`,
        );
      }
      await fetchData();
    } catch {
      hide();
      message.error("전체 갱신에 실패했습니다. 잠시 후 다시 시도하세요.");
    } finally {
      setRefreshing(false);
    }
  }, [fetchData]);

  // ----- Pivoted weekly rows + totals -----
  const weekNumbers = useMemo(() => deriveWeekNumbers(weeklyData), [weeklyData]);
  const pivotedRows = useMemo(() => pivotWeeklyRows(weeklyData), [weeklyData]);
  const totalRow = useMemo(
    () => buildTotalRow(pivotedRows, weekNumbers),
    [pivotedRows, weekNumbers],
  );

  // ----- 통합 요약: 플랫폼별 합산 + 전체 합계 -----
  const platformSummaries = useMemo(
    () => aggregateByPlatform(growthData, weeklyData),
    [growthData, weeklyData],
  );
  const totals = useMemo(
    () => computeTotals(platformSummaries, weeklyData),
    [platformSummaries, weeklyData],
  );

  const weeklyColumns: ColumnsType<PivotedRow> = useMemo(() => {
    const weekColumns: ColumnsType<PivotedRow> = weekNumbers.map((w) => ({
      title: `${w}주 팔로워`,
      key: `week${w}`,
      align: "right",
      render: (_: unknown, record) => formatNumber(record.weeks[w] ?? 0),
    }));
    return [
    {
      title: "어권",
      dataIndex: "language",
      key: "language",
      width: 90,
      render: (val: string) =>
        val === "__total__" ? (
          <strong>합계</strong>
        ) : (
          <Tag color="geekblue" style={{ margin: 0 }}>
            {LANGUAGE_LABELS[val] ?? val}
          </Tag>
        ),
      onCell: (record) =>
        record.key === "__total__" ? { colSpan: 2 } : { colSpan: 1 },
    },
    {
      title: "플랫폼",
      dataIndex: "platform",
      key: "platform",
      width: 110,
      render: (val: string, record) =>
        record.key === "__total__" ? null : (
          <span style={{ fontWeight: 500 }}>
            {PLATFORM_LABELS[val] ?? val}
          </span>
        ),
      onCell: (record) =>
        record.key === "__total__" ? { colSpan: 0 } : { colSpan: 1 },
    },
    ...weekColumns,
    {
      title: "콘텐츠수",
      dataIndex: "postCount",
      key: "postCount",
      align: "right",
      render: (val: number) => formatNumber(val),
    },
    {
      title: "조회수",
      dataIndex: "viewCount",
      key: "viewCount",
      align: "right",
      render: (val: number) => formatNumber(val),
    },
    {
      title: "반응수",
      dataIndex: "reactionCount",
      key: "reactionCount",
      align: "right",
      render: (val: number) => formatNumber(val),
    },
    ];
  }, [weekNumbers]);

  const tableData =
    pivotedRows.length > 0 ? [...pivotedRows, totalRow] : [];

  // ----- Top Posts columns -----
  const topPostColumns: ColumnsType<TopPost> = [
    {
      title: "발행일",
      dataIndex: "posted_at",
      key: "posted_at",
      width: 120,
      render: (val: string) => (val ? dayjs(val).format("YYYY-MM-DD") : "-"),
    },
    {
      title: "어권",
      dataIndex: "language",
      key: "language",
      width: 90,
      render: (val: string) => (
        <Tag color="geekblue" style={{ margin: 0 }}>
          {LANGUAGE_LABELS[val] ?? val}
        </Tag>
      ),
    },
    {
      title: "플랫폼",
      dataIndex: "platform",
      key: "platform",
      width: 110,
      render: (val: string) => (
        <Tag color="purple" style={{ margin: 0 }}>
          {PLATFORM_LABELS[val] ?? val}
        </Tag>
      ),
    },
    {
      title: "제목",
      dataIndex: "title",
      key: "title",
      ellipsis: true,
      render: (val: string) => val ?? "-",
    },
    {
      title: "조회수",
      dataIndex: "view_count",
      key: "view_count",
      width: 110,
      align: "right",
      render: (val: number) => formatNumber(val),
    },
    {
      title: "반응수",
      dataIndex: "total_engagement",
      key: "total_engagement",
      width: 110,
      align: "right",
      render: (val: number) => formatNumber(val),
    },
    {
      title: "",
      dataIndex: "url",
      key: "url",
      width: 80,
      align: "center",
      render: (val: string) =>
        val ? (
          <Button
            type="link"
            size="small"
            icon={<LinkOutlined />}
            onClick={() => window.open(val, "_blank", "noopener,noreferrer")}
          >
            보기
          </Button>
        ) : (
          "-"
        ),
    },
  ];

  return (
    <Spin spinning={loading} size="large">
      <div style={{ maxWidth: 1280, margin: "0 auto" }}>
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 28,
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <h2
            style={{
              margin: 0,
              fontSize: 22,
              fontWeight: 700,
              letterSpacing: "-0.02em",
            }}
          >
            마케팅1팀 — SNS 운영 현황
          </h2>
          <Space size="small" wrap>
            <Select
              value={year}
              options={YEAR_OPTIONS}
              onChange={(val) => setYear(val)}
              style={{ width: 110 }}
              aria-label="년도 선택"
            />
            <Select
              value={month}
              options={MONTH_OPTIONS}
              onChange={(val) => setMonth(val)}
              style={{ width: 90 }}
              aria-label="월 선택"
            />
            <Tooltip title="모든 플랫폼·계정의 팔로워·게시물·지표를 지금 갱신합니다 (수 초~수십 초).">
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                loading={refreshing}
                onClick={() => void handleRefreshAll()}
              >
                전체 갱신
              </Button>
            </Tooltip>
          </Space>
        </div>

        {/* 통합 요약 스트립: 전 플랫폼·전 계정 합산 */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} sm={12} md={6}>
            <Card styles={{ body: { padding: "16px 20px" } }}>
              <Statistic
                title="총 팔로워"
                value={totals.totalFollowers}
                prefix={<TeamOutlined style={{ color: "#1677ff" }} />}
                formatter={(val) => formatNumber(Number(val))}
                valueStyle={{ fontSize: 24, fontWeight: 700 }}
              />
              <div
                style={{
                  marginTop: 6,
                  fontSize: 13,
                  fontWeight: 600,
                  color: totals.followerGrowthRate >= 0 ? "#52c41a" : "#cf1322",
                }}
              >
                {totals.followerGrowthRate >= 0 ? (
                  <ArrowUpOutlined />
                ) : (
                  <ArrowDownOutlined />
                )}{" "}
                {formatPercent(totals.followerGrowthRate * 100)}
                <span style={{ color: "rgba(0,0,0,0.45)", fontWeight: 400, marginLeft: 4 }}>
                  전 주 대비
                </span>
              </div>
            </Card>
          </Col>
          <Col xs={12} sm={12} md={6}>
            <Card styles={{ body: { padding: "16px 20px" } }}>
              <Statistic
                title={`이번 달 게시물 (${month}월)`}
                value={totals.monthPostCount}
                formatter={(val) => formatNumber(Number(val))}
                valueStyle={{ fontSize: 24, fontWeight: 700 }}
                suffix="건"
              />
            </Card>
          </Col>
          <Col xs={12} sm={12} md={6}>
            <Card styles={{ body: { padding: "16px 20px" } }}>
              <Statistic
                title="총 조회수"
                value={totals.totalViews}
                formatter={(val) => formatNumber(Number(val))}
                valueStyle={{ fontSize: 24, fontWeight: 700 }}
              />
            </Card>
          </Col>
          <Col xs={12} sm={12} md={6}>
            <Card styles={{ body: { padding: "16px 20px" } }}>
              <Statistic
                title="평균 참여율"
                value={totals.avgEngagementRate * 100}
                precision={2}
                suffix="%"
                valueStyle={{ fontSize: 24, fontWeight: 700 }}
              />
              <div style={{ marginTop: 6, fontSize: 12, color: "rgba(0,0,0,0.45)" }}>
                반응수 / 조회수
              </div>
            </Card>
          </Col>
        </Row>

        {/* 플랫폼별 카드 행: 계정 집합에서 동적 파생 */}
        {platformSummaries.length > 0 && (
          <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
            {platformSummaries.map((p) => {
              const positive = p.growthRate >= 0;
              const accent = positive ? "#52c41a" : "#cf1322";
              return (
                <Col xs={24} sm={12} md={8} key={p.platform}>
                  <Card hoverable styles={{ body: { padding: "18px 20px" } }}>
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        marginBottom: 12,
                        fontSize: 16,
                        fontWeight: 600,
                      }}
                    >
                      <span style={{ fontSize: 22 }}>
                        {PLATFORM_ICONS[p.platform] ?? null}
                      </span>
                      {PLATFORM_LABELS[p.platform] ?? p.platform}
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
                      <div>
                        <div style={{ fontSize: 12, color: "rgba(0,0,0,0.45)" }}>
                          팔로워
                        </div>
                        <div style={{ fontSize: 22, fontWeight: 700 }}>
                          {formatNumber(p.followers)}
                        </div>
                        <div style={{ fontSize: 12, fontWeight: 600, color: accent, marginTop: 2 }}>
                          {positive ? <ArrowUpOutlined /> : <ArrowDownOutlined />}{" "}
                          {formatPercent(p.growthRate * 100)}
                        </div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div style={{ fontSize: 12, color: "rgba(0,0,0,0.45)" }}>
                          게시물 / 조회수
                        </div>
                        <div style={{ fontSize: 15, fontWeight: 600 }}>
                          {formatNumber(p.postCount)}건
                        </div>
                        <div style={{ fontSize: 13, color: "rgba(0,0,0,0.65)" }}>
                          {formatNumber(p.viewCount)}
                        </div>
                      </div>
                    </div>
                  </Card>
                </Col>
              );
            })}
          </Row>
        )}

        {/* Widget 1: Weekly KPI Table */}
        <Card
          title="주간 KPI"
          extra={
            <span style={{ color: "rgba(0,0,0,0.45)", fontSize: 13 }}>
              {year}년 {month}월
            </span>
          }
          style={{ marginBottom: 16 }}
        >
          <Table<PivotedRow>
            columns={weeklyColumns}
            dataSource={tableData}
            rowKey="key"
            pagination={false}
            size="middle"
            scroll={{ x: 900 }}
            locale={{ emptyText: "데이터가 없습니다" }}
            rowClassName={(record) =>
              record.key === "__total__" ? "tk101-total-row" : ""
            }
          />
          <style>{`
            .tk101-total-row td {
              background: #fafafa !important;
              font-weight: 700;
            }
          `}</style>
        </Card>

        {/* Widget 2: Growth Cards */}
        <Card
          title="채널별 성장률"
          style={{ marginBottom: 16 }}
          styles={{ body: { padding: 16 } }}
        >
          {growthData.length === 0 ? (
            <div
              style={{
                padding: 24,
                textAlign: "center",
                color: "rgba(0,0,0,0.45)",
              }}
            >
              데이터가 없습니다
            </div>
          ) : (
            <Row gutter={[16, 16]}>
              {growthData.map((card) => {
                const isPositive = card.growth_rate >= 0;
                const accent = isPositive ? "#52c41a" : "#cf1322";
                const platformLabel = PLATFORM_LABELS[card.platform] ?? card.platform;
                const languageLabel = LANGUAGE_LABELS[card.language] ?? card.language;
                // 채널 식별: 브랜드 · 플랫폼 · 언어 · 핸들. 백필 전(client=null)이면 브랜드를 생략한다.
                const channelName = `${card.client ? `${card.client} · ` : ""}${platformLabel} · ${languageLabel}${card.handle ? ` · ${card.handle}` : ""}`;
                return (
                  <Col
                    xs={24}
                    sm={12}
                    md={8}
                    lg={6}
                    key={`${card.client ?? ""}-${card.platform}-${card.language}-${card.handle ?? ""}`}
                  >
                    <Card
                      hoverable
                      style={{ borderLeft: `3px solid ${accent}` }}
                      styles={{ body: { padding: "16px 20px" } }}
                    >
                      <div
                        style={{
                          fontSize: 13,
                          color: "rgba(0,0,0,0.55)",
                          marginBottom: 8,
                          fontWeight: 500,
                        }}
                      >
                        {channelName}
                      </div>
                      <Statistic
                        value={card.current_followers}
                        formatter={(val) => formatNumber(Number(val))}
                        valueStyle={{ fontSize: 22, fontWeight: 700 }}
                      />
                      <div
                        style={{
                          marginTop: 8,
                          color: accent,
                          fontWeight: 600,
                          fontSize: 13,
                          display: "flex",
                          alignItems: "center",
                          gap: 4,
                        }}
                      >
                        {isPositive ? (
                          <ArrowUpOutlined />
                        ) : (
                          <ArrowDownOutlined />
                        )}
                        {formatPercent(card.growth_rate)}
                        <span
                          style={{
                            color: "rgba(0,0,0,0.45)",
                            fontWeight: 400,
                            marginLeft: 4,
                          }}
                        >
                          전 주 대비
                        </span>
                      </div>
                    </Card>
                  </Col>
                );
              })}
            </Row>
          )}
        </Card>

        {/* Widget 3: Top Posts */}
        <Card
          title="인기 콘텐츠 Top 5"
          style={{ marginBottom: 16 }}
          extra={
            <Space size="small">
              <Select
                value={topLanguage}
                options={LANGUAGE_OPTIONS}
                onChange={(val) => setTopLanguage(val)}
                style={{ width: 130 }}
                aria-label="어권 필터"
              />
              <Select
                value={topPlatform}
                options={PLATFORM_OPTIONS}
                onChange={(val) => setTopPlatform(val)}
                style={{ width: 140 }}
                aria-label="플랫폼 필터"
              />
            </Space>
          }
        >
          <Table<TopPost>
            columns={topPostColumns}
            dataSource={topPosts}
            rowKey="id"
            pagination={false}
            size="middle"
            scroll={{ x: 760 }}
            locale={{ emptyText: "데이터가 없습니다" }}
          />
        </Card>

        {/* Widget 4: 팔로워 추이 (주차별 멀티라인, 채널별 시리즈) */}
        <Card title="팔로워 추이 (최근 6개월)">
          <FollowerTrendChart data={trendData} />
        </Card>
      </div>
    </Spin>
  );
}
