import { Button, Card, Select, Space, Spin, Tooltip } from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import FollowerTrendChart from "../../components/sns/FollowerTrendChart";
import { MONTH_OPTIONS, YEAR_OPTIONS } from "./marketing1/constants";
import { useMarketing1Data } from "./marketing1/useMarketing1Data";
import SummaryStrip from "./marketing1/SummaryStrip";
import WeeklyKpiTable from "./marketing1/WeeklyKpiTable";
import GrowthCards from "./marketing1/growthCards";
import TopPostsTable from "./marketing1/TopPostsTable";

export default function Marketing1Dashboard() {
  const {
    year,
    setYear,
    month,
    setMonth,
    topLanguage,
    setTopLanguage,
    topPlatform,
    setTopPlatform,
    growthData,
    topPosts,
    trendData,
    loading,
    refreshing,
    handleRefreshAll,
    weekNumbers,
    pivotedRows,
    totalRow,
    platformSummaries,
    totals,
  } = useMarketing1Data();

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

        <SummaryStrip
          month={month}
          totals={totals}
          platformSummaries={platformSummaries}
        />

        {/* Widget 1: Weekly KPI Table */}
        <WeeklyKpiTable
          year={year}
          month={month}
          weekNumbers={weekNumbers}
          pivotedRows={pivotedRows}
          totalRow={totalRow}
        />

        {/* Widget 2: Growth Cards */}
        <GrowthCards growthData={growthData} />

        {/* Widget 3: Top Posts */}
        <TopPostsTable
          topPosts={topPosts}
          topLanguage={topLanguage}
          setTopLanguage={setTopLanguage}
          topPlatform={topPlatform}
          setTopPlatform={setTopPlatform}
        />

        {/* Widget 4: 팔로워 추이 (주차별 멀티라인, 채널별 시리즈) */}
        <Card title="팔로워 추이 (최근 6개월)">
          <FollowerTrendChart data={trendData} />
        </Card>
      </div>
    </Spin>
  );
}
