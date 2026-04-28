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
} from "antd";
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  LinkOutlined,
} from "@ant-design/icons";
import { useEffect, useMemo, useState, useCallback } from "react";
import dayjs from "dayjs";
import api from "../../api/client";
import type { ColumnsType } from "antd/es/table";

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
  week1: number;
  week2: number;
  week3: number;
  week4: number;
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

// Pivot: (language, platform, week_number) → row per (language+platform) with week columns
function pivotWeeklyRows(rows: WeeklyKpiRow[]): PivotedRow[] {
  const grouped = new Map<string, PivotedRow>();
  for (const row of rows) {
    const key = `${row.language}__${row.platform}`;
    const existing = grouped.get(key) ?? {
      key,
      language: row.language,
      platform: row.platform,
      week1: 0,
      week2: 0,
      week3: 0,
      week4: 0,
      postCount: 0,
      viewCount: 0,
      reactionCount: 0,
    };
    const next: PivotedRow = { ...existing };
    if (row.week_number === 1) next.week1 = row.followers;
    if (row.week_number === 2) next.week2 = row.followers;
    if (row.week_number === 3) next.week3 = row.followers;
    if (row.week_number === 4) next.week4 = row.followers;
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

function buildTotalRow(rows: PivotedRow[]): PivotedRow {
  return rows.reduce<PivotedRow>(
    (acc, row) => ({
      ...acc,
      week1: acc.week1 + row.week1,
      week2: acc.week2 + row.week2,
      week3: acc.week3 + row.week3,
      week4: acc.week4 + row.week4,
      postCount: acc.postCount + row.postCount,
      viewCount: acc.viewCount + row.viewCount,
      reactionCount: acc.reactionCount + row.reactionCount,
    }),
    {
      key: "__total__",
      language: "__total__",
      platform: "__total__",
      week1: 0,
      week2: 0,
      week3: 0,
      week4: 0,
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

export default function Marketing1Dashboard() {
  const [year, setYear] = useState<number>(dayjs().year());
  const [month, setMonth] = useState<number>(dayjs().month() + 1);

  const [weeklyData, setWeeklyData] = useState<WeeklyKpiRow[]>([]);
  const [growthData, setGrowthData] = useState<GrowthCard[]>([]);
  const [topPosts, setTopPosts] = useState<TopPost[]>([]);

  const [topLanguage, setTopLanguage] = useState<string>("all");
  const [topPlatform, setTopPlatform] = useState<string>("all");

  const [loading, setLoading] = useState<boolean>(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const topParams: Record<string, string | number> = { limit: 5 };
      if (topLanguage !== "all") topParams.language = topLanguage;
      if (topPlatform !== "all") topParams.platform = topPlatform;

      const [weeklyRes, growthRes, topRes] = await Promise.all([
        api.get<WeeklyKpiRow[]>("/api/sns/stats/weekly", {
          params: { year, month },
        }),
        api.get<GrowthCard[]>("/api/sns/stats/growth"),
        api.get<TopPost[]>("/api/sns/stats/top-posts", { params: topParams }),
      ]);
      setWeeklyData(weeklyRes.data ?? []);
      setGrowthData(growthRes.data ?? []);
      setTopPosts(topRes.data ?? []);
    } catch {
      message.error("대시보드 데이터를 불러오는데 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, [year, month, topLanguage, topPlatform]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // ----- Pivoted weekly rows + totals -----
  const pivotedRows = useMemo(() => pivotWeeklyRows(weeklyData), [weeklyData]);
  const totalRow = useMemo(() => buildTotalRow(pivotedRows), [pivotedRows]);

  const weeklyColumns: ColumnsType<PivotedRow> = [
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
    {
      title: "1주 팔로워",
      dataIndex: "week1",
      key: "week1",
      align: "right",
      render: (val: number) => formatNumber(val),
    },
    {
      title: "2주 팔로워",
      dataIndex: "week2",
      key: "week2",
      align: "right",
      render: (val: number) => formatNumber(val),
    },
    {
      title: "3주 팔로워",
      dataIndex: "week3",
      key: "week3",
      align: "right",
      render: (val: number) => formatNumber(val),
    },
    {
      title: "4주 팔로워",
      dataIndex: "week4",
      key: "week4",
      align: "right",
      render: (val: number) => formatNumber(val),
    },
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
          </Space>
        </div>

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
                const channelName = `${PLATFORM_LABELS[card.platform] ?? card.platform} (${LANGUAGE_LABELS[card.language] ?? card.language})`;
                return (
                  <Col
                    xs={24}
                    sm={12}
                    md={8}
                    lg={6}
                    key={`${card.language}-${card.platform}`}
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

        {/* Widget 4: Trend (placeholder) */}
        <Card
          title="주차별 트렌드"
          extra={<Tag color="orange">준비 중</Tag>}
        >
          <div
            style={{
              padding: "48px 16px",
              textAlign: "center",
              color: "rgba(0,0,0,0.45)",
              background:
                "repeating-linear-gradient(135deg, #fafafa 0px, #fafafa 12px, #f5f5f5 12px, #f5f5f5 24px)",
              borderRadius: 6,
            }}
          >
            준비 중입니다. v0.5.x에서 주차별 트렌드 차트가 추가될 예정입니다.
          </div>
        </Card>
      </div>
    </Spin>
  );
}
