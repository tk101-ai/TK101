import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Input,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
  message,
} from "antd";
import {
  DollarOutlined,
  ReloadOutlined,
  SearchOutlined,
  SendOutlined,
  UndoOutlined,
  WarningOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type { TabsProps } from "antd";
import dayjs, { Dayjs } from "dayjs";
import {
  getCostByDay,
  getCostByPersona,
  getSendFailures,
  getSessionStatusCounts,
  searchMessages,
  type CostByDayItem,
  type CostByPersonaItem,
  type MessageSearchItem,
  type SendFailureItem,
} from "../../api/distribution_analytics";
import {
  COMPANY_FILTER_OPTIONS,
  type DistributionCompany,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";

type CompanyChoice = DistributionCompany | "all";

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

// ---------------------------------------------------------------------------
// 공통 헬퍼
// ---------------------------------------------------------------------------

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dayjs(iso).format("YYYY-MM-DD");
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dayjs(iso).format("YYYY-MM-DD HH:mm");
}

function formatCostUsd(value: string | number | null | undefined): string {
  if (value == null || value === "") return "$0.0000";
  const n = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(n)) return "—";
  return `$${n.toFixed(4)}`;
}

function sumCostUsd(values: { total_cost_usd: string }[]): number {
  return values.reduce((acc, row) => {
    const n = Number(row.total_cost_usd);
    return acc + (Number.isFinite(n) ? n : 0);
  }, 0);
}

const SESSION_STATUS_KEYS = [
  "pending",
  "approved",
  "rejected",
  "sending",
  "sent",
  "failed",
] as const;

const SESSION_STATUS_LABEL: Record<string, string> = {
  pending: "검수 대기",
  approved: "승인됨",
  rejected: "거부됨",
  sending: "송신 중",
  sent: "송신 완료",
  failed: "실패",
};

const SESSION_STATUS_COLOR: Record<string, string> = {
  pending: "#faad14",
  approved: "#52c41a",
  rejected: "#bfbfbf",
  sending: "#1677ff",
  sent: "#3f8600",
  failed: "#cf1322",
};

const MESSAGE_STATUS_COLOR: Record<string, string> = {
  queued: "default",
  sent: "green",
  failed: "red",
  skipped: "gold",
};

interface RangeFilter {
  from?: string;
  to?: string;
  /**
   * 회사 필터 — 백엔드 analytics endpoints 가 아직 미지원일 수 있음.
   * UI 표시·향후 호환용으로만 유지. 현재 빌드된 endpoints 는 무시 처리.
   */
  company_label?: string;
}

function rangeToFilter(
  range: [Dayjs | null, Dayjs | null] | null,
  company: CompanyChoice,
): RangeFilter {
  const [from, to] = range ?? [null, null];
  return {
    from: from ? from.format("YYYY-MM-DD") : undefined,
    to: to ? to.format("YYYY-MM-DD") : undefined,
    company_label: company === "all" ? undefined : company,
  };
}

// ---------------------------------------------------------------------------
// Tab 1: 비용
// ---------------------------------------------------------------------------

interface CostTabProps {
  filter: RangeFilter;
}

function CostTab({ filter }: CostTabProps) {
  const [byDay, setByDay] = useState<CostByDayItem[]>([]);
  const [byPersona, setByPersona] = useState<CostByPersonaItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [day, persona] = await Promise.all([
        getCostByDay(filter.from, filter.to),
        getCostByPersona(filter.from, filter.to),
      ]);
      setByDay(day);
      setByPersona(persona);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "비용 데이터 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [filter.from, filter.to]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const totals = useMemo(() => {
    const totalCost = sumCostUsd(byDay);
    const totalSessions = byDay.reduce((a, r) => a + r.session_count, 0);
    return { totalCost, totalSessions };
  }, [byDay]);

  const dayColumns: ColumnsType<CostByDayItem> = [
    {
      title: "날짜",
      dataIndex: "date",
      width: 140,
      render: (v: string) => <Text strong>{formatDate(v)}</Text>,
    },
    {
      title: "비용 (USD)",
      dataIndex: "total_cost_usd",
      width: 160,
      align: "right",
      render: (v: string) => (
        <span style={{ fontFamily: "monospace", fontSize: 13 }}>
          {formatCostUsd(v)}
        </span>
      ),
    },
    {
      title: "세션 수",
      dataIndex: "session_count",
      width: 100,
      align: "right",
      render: (v: number) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{v}</span>
      ),
    },
  ];

  const personaColumns: ColumnsType<CostByPersonaItem> = [
    {
      title: "페르소나",
      dataIndex: "account_label",
      width: 160,
      render: (v: string) => <Tag color="geekblue">{v}</Tag>,
    },
    {
      title: "비용 (USD)",
      dataIndex: "total_cost_usd",
      width: 160,
      align: "right",
      render: (v: string) => (
        <span style={{ fontFamily: "monospace", fontSize: 13 }}>
          {formatCostUsd(v)}
        </span>
      ),
    },
    {
      title: "세션 수",
      dataIndex: "session_count",
      width: 100,
      align: "right",
      render: (v: number) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{v}</span>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="기간 총 비용"
              value={totals.totalCost}
              precision={4}
              prefix="$"
              valueStyle={{ color: "#cf1322" }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="기간 세션 수" value={totals.totalSessions} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="세션당 평균"
              value={
                totals.totalSessions > 0
                  ? totals.totalCost / totals.totalSessions
                  : 0
              }
              precision={4}
              prefix="$"
            />
          </Card>
        </Col>
      </Row>

      <Card title="일별 비용" size="small">
        <Table
          columns={dayColumns}
          dataSource={byDay}
          rowKey="date"
          loading={loading}
          size="small"
          pagination={{ pageSize: 14, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="해당 기간에 비용 기록이 없습니다"
              />
            ),
          }}
        />
      </Card>

      <Card title="페르소나(발신자)별 비용" size="small">
        <Table
          columns={personaColumns}
          dataSource={byPersona}
          rowKey="persona_id"
          loading={loading}
          size="small"
          pagination={{ pageSize: 10, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="해당 기간에 발신 페르소나가 없습니다"
              />
            ),
          }}
        />
      </Card>
    </Space>
  );
}

// ---------------------------------------------------------------------------
// Tab 2: 송신 결과
// ---------------------------------------------------------------------------

interface SendTabProps {
  filter: RangeFilter;
}

function SendTab({ filter }: SendTabProps) {
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [failures, setFailures] = useState<SendFailureItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [c, f] = await Promise.all([
        getSessionStatusCounts(filter.from, filter.to),
        getSendFailures(filter.from, filter.to),
      ]);
      setCounts(c);
      setFailures(f);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "송신 통계 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [filter.from, filter.to]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const failureColumns: ColumnsType<SendFailureItem> = [
    {
      title: "에러 코드",
      dataIndex: "error_code",
      width: 220,
      render: (v: string) => (
        <Tag color={v === "UNKNOWN" ? "default" : "red"}>
          <span style={{ fontFamily: "monospace" }}>{v}</span>
        </Tag>
      ),
    },
    {
      title: "발생 횟수",
      dataIndex: "count",
      width: 120,
      align: "right",
      render: (v: number) => (
        <Text strong style={{ fontVariantNumeric: "tabular-nums" }}>
          {v}
        </Text>
      ),
    },
    {
      title: "마지막 시도",
      dataIndex: "last_attempted_at",
      width: 180,
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {formatDateTime(v)}
        </Text>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={[12, 12]}>
        {SESSION_STATUS_KEYS.map((key) => (
          <Col xs={12} sm={8} md={4} key={key}>
            <Card size="small" loading={loading}>
              <Statistic
                title={SESSION_STATUS_LABEL[key]}
                value={counts[key] ?? 0}
                valueStyle={{ color: SESSION_STATUS_COLOR[key], fontSize: 22 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card
        title={
          <Space>
            <WarningOutlined style={{ color: "#cf1322" }} />
            <span>송신 실패 원인 분류</span>
          </Space>
        }
        size="small"
      >
        <Table
          columns={failureColumns}
          dataSource={failures}
          rowKey="error_code"
          loading={loading}
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="해당 기간에 송신 실패 기록이 없습니다"
              />
            ),
          }}
        />
      </Card>
    </Space>
  );
}

// ---------------------------------------------------------------------------
// Tab 3: 메시지 검색
// ---------------------------------------------------------------------------

interface SearchTabProps {
  filter: RangeFilter;
}

function SearchTab({ filter }: SearchTabProps) {
  const [query, setQuery] = useState<string>("");
  const [results, setResults] = useState<MessageSearchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = useCallback(
    async (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) {
        message.warning("검색어를 입력하세요");
        return;
      }
      setLoading(true);
      setHasSearched(true);
      try {
        const items = await searchMessages(trimmed, filter.from, filter.to, 200);
        setResults(items);
        if (items.length === 0) {
          message.info("검색 결과가 없습니다");
        }
      } catch (err: unknown) {
        message.error(extractErrorDetail(err, "메시지 검색 실패"));
      } finally {
        setLoading(false);
      }
    },
    [filter.from, filter.to],
  );

  const columns: ColumnsType<MessageSearchItem> = [
    {
      title: "시나리오",
      dataIndex: "scenario_name",
      width: 180,
      render: (v: string) => <Tag color="purple">{v}</Tag>,
    },
    {
      title: "발신자",
      dataIndex: "sender_account_label",
      width: 120,
      render: (v: string) => <Tag color="geekblue">{v}</Tag>,
    },
    {
      title: "메시지 내용",
      dataIndex: "content",
      ellipsis: { showTitle: true },
      render: (v: string) => (
        <Text
          style={{
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
            fontSize: 13,
          }}
          title={v}
        >
          {v}
        </Text>
      ),
    },
    {
      title: "송신일",
      dataIndex: "sent_at",
      width: 160,
      render: (v: string | null) => (
        <Text type={v ? undefined : "secondary"} style={{ fontSize: 12 }}>
          {formatDateTime(v)}
        </Text>
      ),
    },
    {
      title: "상태",
      dataIndex: "status",
      width: 100,
      render: (v: string) => (
        <Tag color={MESSAGE_STATUS_COLOR[v] ?? "default"}>{v}</Tag>
      ),
    },
    {
      title: "작업",
      key: "actions",
      width: 110,
      render: (_: unknown, record: MessageSearchItem) => (
        <Link to={`/distribution/sessions/${record.session_id}`}>
          <Button type="link" size="small">
            세션 보기
          </Button>
        </Link>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card size="small">
        <Space size={12} wrap>
          <Input.Search
            placeholder="메시지 본문에서 검색 (예: '입금', '재고')"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onSearch={handleSearch}
            enterButton={
              <Button type="primary" icon={<SearchOutlined />}>
                검색
              </Button>
            }
            allowClear
            style={{ width: 480 }}
            maxLength={100}
            loading={loading}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            • 대소문자 무관, content / edited_content 모두 매칭
          </Text>
        </Space>
      </Card>

      <Card
        title={
          hasSearched
            ? `검색 결과 (${results.length}건)`
            : "검색어를 입력하세요"
        }
        size="small"
      >
        <Table
          columns={columns}
          dataSource={results}
          rowKey="message_id"
          loading={loading}
          size="small"
          scroll={{ x: 1000 }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  hasSearched
                    ? "검색 결과가 없습니다"
                    : "위 입력창에 키워드를 입력하고 엔터를 누르세요"
                }
              />
            ),
          }}
        />
      </Card>
    </Space>
  );
}

// ---------------------------------------------------------------------------
// Tab 4: 세션 추이
// ---------------------------------------------------------------------------

interface SessionTrendTabProps {
  filter: RangeFilter;
}

function SessionTrendTab({ filter }: SessionTrendTabProps) {
  const [byDay, setByDay] = useState<CostByDayItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const day = await getCostByDay(filter.from, filter.to);
      setByDay(day);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "세션 추이 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [filter.from, filter.to]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const totalSessions = useMemo(
    () => byDay.reduce((a, r) => a + r.session_count, 0),
    [byDay],
  );
  const peakDay = useMemo(() => {
    let peak: CostByDayItem | null = null;
    for (const row of byDay) {
      if (!peak || row.session_count > peak.session_count) peak = row;
    }
    return peak;
  }, [byDay]);

  const columns: ColumnsType<CostByDayItem> = [
    {
      title: "날짜",
      dataIndex: "date",
      width: 140,
      render: (v: string) => <Text strong>{formatDate(v)}</Text>,
    },
    {
      title: "세션 수",
      dataIndex: "session_count",
      width: 120,
      align: "right",
      render: (v: number) => (
        <Text
          strong
          style={{ fontVariantNumeric: "tabular-nums", color: "#1677ff" }}
        >
          {v}
        </Text>
      ),
    },
    {
      title: "비용 (USD)",
      dataIndex: "total_cost_usd",
      width: 160,
      align: "right",
      render: (v: string) => (
        <span style={{ fontFamily: "monospace", fontSize: 13 }}>
          {formatCostUsd(v)}
        </span>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="기간 총 세션" value={totalSessions} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="피크 일자"
              value={peakDay ? formatDate(peakDay.date) : "—"}
              valueStyle={{ fontSize: 18 }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="피크 일자 세션 수"
              value={peakDay?.session_count ?? 0}
              valueStyle={{ color: "#1677ff" }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="일별 세션 생성 추이" size="small">
        <Table
          columns={columns}
          dataSource={byDay}
          rowKey="date"
          loading={loading}
          size="small"
          pagination={{ pageSize: 14, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="해당 기간에 세션 기록이 없습니다"
              />
            ),
          }}
        />
      </Card>
    </Space>
  );
}

// ---------------------------------------------------------------------------
// 메인 페이지
// ---------------------------------------------------------------------------

const DEFAULT_RANGE_DAYS = 30;

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
