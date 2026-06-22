import { useMemo, useState } from "react";
import { Button, DatePicker, Select, Space, Tabs, Typography } from "antd";
import {
  DollarOutlined,
  ReloadOutlined,
  SearchOutlined,
  SendOutlined,
  UndoOutlined,
} from "@ant-design/icons";
import type { TabsProps } from "antd";
import dayjs, { Dayjs } from "dayjs";
import { COMPANY_FILTER_OPTIONS } from "../../api/distribution";
import { CostTab } from "./analytics/CostTab";
import { SendTab } from "./analytics/SendTab";
import { SearchTab } from "./analytics/SearchTab";
import { SessionTrendTab } from "./analytics/SessionTrendTab";
import { rangeToFilter } from "./analytics/format";
import { DEFAULT_RANGE_DAYS } from "./analytics/constants";
import type { CompanyChoice, RangeFilter } from "./analytics/types";

const { Title, Paragraph, Text } = Typography;
const { RangePicker } = DatePicker;

/**
 * 신사업유통 분석 페이지 (T9 Phase E-4 — admin 전용).
 *
 * 대시보드와 분리된 별도 페이지. 4개 탭으로 운영 모니터링·디버깅·비용 추적.
 *  Tab 1: 비용 — 일별 + 페르소나별 + 합계 Statistic
 *  Tab 2: 송신 결과 — status 6종 Statistic + 실패 원인 분류
 *  Tab 3: 메시지 검색 — content/edited_content ILIKE
 *  Tab 4: 세션 추이 — 일별 세션 생성 수 (cost_by_day 의 session_count 재사용)
 *
 * RangePicker 기본값: 최근 30일.
 */

export default function AnalyticsPage() {
  const [range, setRange] = useState<[Dayjs | null, Dayjs | null] | null>(
    () => [dayjs().subtract(DEFAULT_RANGE_DAYS, "day"), dayjs()],
  );
  const [company, setCompany] = useState<CompanyChoice>("all");
  const [activeTab, setActiveTab] = useState<string>("cost");
  // 새로고침은 RangePicker 변경 + 탭 컴포넌트의 useEffect 가 알아서 처리.
  // 명시적 재호출이 필요할 때만 키 갱신.
  const [refreshKey, setRefreshKey] = useState<number>(0);

  const filter: RangeFilter = useMemo(
    () => rangeToFilter(range, company),
    [range, company],
  );

  const handleReset = () => {
    setRange([dayjs().subtract(DEFAULT_RANGE_DAYS, "day"), dayjs()]);
    setCompany("all");
  };

  const tabs: TabsProps["items"] = [
    {
      key: "cost",
      label: (
        <Space size={6}>
          <DollarOutlined />
          <span>비용</span>
        </Space>
      ),
      children: <CostTab key={`cost-${refreshKey}`} filter={filter} />,
    },
    {
      key: "send",
      label: (
        <Space size={6}>
          <SendOutlined />
          <span>송신 결과</span>
        </Space>
      ),
      children: <SendTab key={`send-${refreshKey}`} filter={filter} />,
    },
    {
      key: "search",
      label: (
        <Space size={6}>
          <SearchOutlined />
          <span>메시지 검색</span>
        </Space>
      ),
      children: <SearchTab key={`search-${refreshKey}`} filter={filter} />,
    },
    {
      key: "trend",
      label: (
        <Space size={6}>
          <ReloadOutlined />
          <span>세션 추이</span>
        </Space>
      ),
      children: <SessionTrendTab key={`trend-${refreshKey}`} filter={filter} />,
    },
  ];

  return (
    <div style={{ maxWidth: 1480 }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          분석 / 비용
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          Claude API 비용 추세, 송신 성공/실패율, 과거 메시지를 한 화면에서
          모니터링하고 디버깅합니다. 메시지 검색은 본문 / 편집본 모두 매칭합니다.
        </Paragraph>
      </div>

      {/* 기간 필터 — 메시지 검색 탭 제외 모든 탭이 공유 */}
      <div
        style={{
          marginBottom: 16,
          padding: "12px 16px",
          background: "#fafafa",
          borderRadius: 6,
          display: "flex",
          alignItems: "center",
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <Text strong style={{ marginRight: 4 }}>
          회사
        </Text>
        <Select<CompanyChoice>
          value={company}
          onChange={(v) => setCompany(v)}
          options={COMPANY_FILTER_OPTIONS}
          style={{ width: 200 }}
        />
        <Text strong style={{ marginLeft: 8, marginRight: 4 }}>
          기간 필터
        </Text>
        <RangePicker
          value={range}
          onChange={(v) =>
            setRange(v ? [v[0] ?? null, v[1] ?? null] : null)
          }
          format="YYYY-MM-DD"
          allowClear
          placeholder={["시작일", "종료일"]}
        />
        <Button
          icon={<UndoOutlined />}
          onClick={handleReset}
          title="회사 전체 + 최근 30일로 초기화"
        >
          초기화
        </Button>
        <Button
          icon={<ReloadOutlined />}
          onClick={() => setRefreshKey((k) => k + 1)}
          title="현재 탭 다시 조회"
        >
          새로고침
        </Button>
        {activeTab === "search" && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            • 메시지 검색은 기간 필터를 옵션으로 사용합니다
          </Text>
        )}
        {company !== "all" && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            • 회사 필터: backend analytics endpoint 가 미지원 시 전체 데이터가
            반환될 수 있습니다
          </Text>
        )}
      </div>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={tabs}
        size="large"
        destroyOnHidden
      />
    </div>
  );
}
