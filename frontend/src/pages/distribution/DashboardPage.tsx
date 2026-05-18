import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Progress,
  Row,
  Space,
  Spin,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs, { type Dayjs } from "dayjs";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  DASHBOARD_STATUS_COLOR,
  DASHBOARD_STATUS_LABEL,
  type BrandDistItem,
  type CategoryDistItem,
  type OverviewOut,
  type SendSuccessRateOut,
  type StatusBreakdownItem,
  type WeeklyTrendItem,
  getBrandDist,
  getCategoryDist,
  getOverview,
  getSendSuccessRate,
  getSessionBreakdown,
  getWeeklyTrends,
} from "../../api/distribution_dashboard";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;
const { RangePicker } = DatePicker;

/**
 * 신사업유통 대시보드 페이지 (T9 Phase E-1, admin 전용).
 *
 * 영역:
 * 1. KPI 카드 8개 — 매입/매출/입금, 제품/재고/세션/송신 성공률.
 * 2. 주차별 추이 (Line) — KR매입 · VN재고이동 · VN매출 · 입금합계.
 * 3. 카테고리 분포 (Pie) — product_count 기준.
 * 4. 세션 상태 분포 (Bar) — 6 status 항상 표시.
 * 5. 상위 브랜드 (Table) — 재고 기준 Top 10.
 *
 * 기간 필터(RangePicker)는 weekly/sessions/success_rate 만 영향.
 * 카테고리/브랜드 분포는 시점 데이터(products)라 기간 무관.
 */

type DateRange = [Dayjs | null, Dayjs | null] | null;

const NUMBER_FORMATTER = new Intl.NumberFormat("ko-KR");

function formatNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return NUMBER_FORMATTER.format(Math.round(value));
}

function formatMoney(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return NUMBER_FORMATTER.format(Math.round(value));
}

function formatPercent(rate: number): string {
  if (!Number.isFinite(rate)) return "—";
  return `${(rate * 100).toFixed(1)}%`;
}

function toIsoDate(d: Dayjs | null | undefined): string | undefined {
  if (!d) return undefined;
  return d.format("YYYY-MM-DD");
}

const CATEGORY_COLORS: string[] = [
  "#1677ff",
  "#52c41a",
  "#faad14",
  "#eb2f96",
  "#722ed1",
  "#13c2c2",
  "#fa8c16",
  "#a0d911",
  "#f5222d",
  "#2f54eb",
];

interface PeriodScopedState {
  overview: OverviewOut | null;
  weekly: WeeklyTrendItem[];
  sessions: StatusBreakdownItem[];
  success: SendSuccessRateOut | null;
}

interface PeriodInvariantState {
  category: CategoryDistItem[];
  brand: BrandDistItem[];
}

export default function DashboardPage() {
  const [range, setRange] = useState<DateRange>(null);
  const [scoped, setScoped] = useState<PeriodScopedState>({
    overview: null,
    weekly: [],
    sessions: [],
    success: null,
  });
  const [invariant, setInvariant] = useState<PeriodInvariantState>({
    category: [],
    brand: [],
  });
  const [loadingScoped, setLoadingScoped] = useState(false);
  const [loadingInvariant, setLoadingInvariant] = useState(false);

  const fromIso = useMemo(() => toIsoDate(range?.[0]), [range]);
  const toIso = useMemo(() => toIsoDate(range?.[1]), [range]);

  const fetchScoped = useCallback(async () => {
    setLoadingScoped(true);
    try {
      const [overview, weekly, sessions, success] = await Promise.all([
        getOverview(fromIso, toIso),
        getWeeklyTrends(fromIso, toIso),
        getSessionBreakdown(fromIso, toIso),
        getSendSuccessRate(fromIso, toIso),
      ]);
      setScoped({ overview, weekly, sessions, success });
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "대시보드 KPI 조회 실패"));
    } finally {
      setLoadingScoped(false);
    }
  }, [fromIso, toIso]);

  const fetchInvariant = useCallback(async () => {
    setLoadingInvariant(true);
    try {
      const [category, brand] = await Promise.all([
        getCategoryDist(),
        getBrandDist(10),
      ]);
      setInvariant({ category, brand });
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "분포 데이터 조회 실패"));
    } finally {
      setLoadingInvariant(false);
    }
  }, []);

  useEffect(() => {
    const run = async () => {
      await fetchScoped();
    };
    void run();
  }, [fetchScoped]);

  useEffect(() => {
    const run = async () => {
      await fetchInvariant();
    };
    void run();
  }, [fetchInvariant]);

  const handleRefresh = () => {
    void fetchScoped();
    void fetchInvariant();
  };

  const handleRangeChange = (next: DateRange) => {
    setRange(next);
  };

  const weeklyChartData = useMemo(
    () =>
      scoped.weekly.map((row) => ({
        ...row,
        label: row.period_label || dayjs(row.period_start).format("MM/DD"),
      })),
    [scoped.weekly],
  );

  const categoryChartData = useMemo(
    () =>
      invariant.category.map((row) => ({
        name: row.category,
        value: row.product_count,
        stock: row.total_stock_qty,
      })),
    [invariant.category],
  );

  const sessionChartData = useMemo(
    () =>
      scoped.sessions.map((row) => ({
        statusKey: row.status,
        statusLabel: DASHBOARD_STATUS_LABEL[row.status] ?? row.status,
        count: row.count,
        color: DASHBOARD_STATUS_COLOR[row.status] ?? "#8c8c8c",
      })),
    [scoped.sessions],
  );

  const brandColumns: ColumnsType<BrandDistItem> = [
    {
      title: "#",
      key: "rank",
      width: 50,
      align: "center" as const,
      render: (_: unknown, _row: BrandDistItem, index: number) => (
        <Text strong>{index + 1}</Text>
      ),
    },
    {
      title: "브랜드",
      dataIndex: "brand",
      ellipsis: true,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: "제품 수",
      dataIndex: "product_count",
      width: 100,
      align: "right" as const,
      render: (v: number) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {formatNumber(v)}
        </span>
      ),
    },
    {
      title: "총 재고",
      dataIndex: "total_stock_qty",
      width: 140,
      align: "right" as const,
      render: (v: number) => (
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 13,
            fontVariantNumeric: "tabular-nums",
          }}
        >
          {formatNumber(v)}
        </span>
      ),
    },
  ];

  const overview = scoped.overview;
  const success = scoped.success;
  const successPercent = success ? Math.round(success.success_rate * 100) : 0;

  return (
    <div style={{ maxWidth: 1680 }}>
      <div
        style={{
          marginBottom: 24,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 16,
          flexWrap: "wrap",
        }}
      >
        <div>
          <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
            신사업유통 대시보드
          </Title>
          <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
            기간을 선택하면 매입·매출·세션·송신 위젯이 해당 기간으로
            재집계됩니다. 카테고리·브랜드 분포는 현재 시점 데이터로 표시됩니다.
          </Paragraph>
        </div>
        <Space>
          <RangePicker
            value={range ?? undefined}
            onChange={(next) => handleRangeChange(next as DateRange)}
            allowEmpty={[true, true]}
            allowClear
            placeholder={["시작일", "종료일"]}
          />
          <Button
            icon={<ReloadOutlined />}
            onClick={handleRefresh}
            loading={loadingScoped || loadingInvariant}
          >
            새로고침
          </Button>
        </Space>
      </div>

      <Spin spinning={loadingScoped} tip="KPI 집계 중...">
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="KR 매입"
                value={formatMoney(overview?.total_kr_purchase)}
                valueStyle={{ color: "#1677ff" }}
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="VN 재고이동"
                value={formatMoney(overview?.total_vn_inventory_move)}
                valueStyle={{ color: "#13c2c2" }}
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="VN 매출완료"
                value={formatMoney(overview?.total_vn_sales)}
                valueStyle={{ color: "#52c41a" }}
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="입금요청 합계"
                value={formatMoney(overview?.total_deposit_req)}
                valueStyle={{ color: "#fa8c16" }}
              />
            </Card>
          </Col>
        </Row>

        <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="제품 수"
                value={formatNumber(overview?.product_count)}
                suffix="개"
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="총 재고"
                value={formatNumber(overview?.total_stock_qty)}
                suffix="개"
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="세션 수"
                value={formatNumber(overview?.session_count)}
                suffix="건"
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Space direction="vertical" size={4} style={{ width: "100%" }}>
                <Text type="secondary" style={{ fontSize: 14 }}>
                  송신 성공률
                </Text>
                <Progress
                  percent={successPercent}
                  size={[180, 12]}
                  strokeColor="#52c41a"
                  format={(p) => `${p ?? 0}%`}
                />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {success
                    ? `성공 ${formatNumber(success.success_count)} / 실패 ${formatNumber(success.failed_count)} / 총 ${formatNumber(success.total_attempts)}`
                    : "—"}
                </Text>
              </Space>
            </Card>
          </Col>
        </Row>
      </Spin>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={14}>
          <Card
            title="주차별 추이"
            extra={
              <Text type="secondary" style={{ fontSize: 12 }}>
                period_start 오름차순
              </Text>
            }
          >
            <div style={{ width: "100%", height: 360 }}>
              {weeklyChartData.length === 0 ? (
                <Empty
                  description="해당 기간 데이터 없음"
                  style={{ paddingTop: 80 }}
                />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart
                    data={weeklyChartData}
                    margin={{ top: 16, right: 24, bottom: 8, left: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                    <YAxis
                      tick={{ fontSize: 12 }}
                      tickFormatter={(v) => formatNumber(Number(v))}
                    />
                    <RechartsTooltip
                      formatter={(value: number | string) =>
                        formatMoney(Number(value))
                      }
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Line
                      type="monotone"
                      dataKey="kr_purchase"
                      name="KR매입"
                      stroke="#1677ff"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="vn_inventory_move"
                      name="VN재고이동"
                      stroke="#13c2c2"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="vn_sales_completed"
                      name="VN매출완료"
                      stroke="#52c41a"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                    <Line
                      type="monotone"
                      dataKey="deposit_total"
                      name="입금합계"
                      stroke="#fa8c16"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={10}>
          <Card
            title="카테고리 분포"
            extra={
              <Text type="secondary" style={{ fontSize: 12 }}>
                제품 수 기준
              </Text>
            }
            loading={loadingInvariant}
          >
            <div style={{ width: "100%", height: 360 }}>
              {categoryChartData.length === 0 ? (
                <Empty
                  description="카테고리 데이터 없음"
                  style={{ paddingTop: 80 }}
                />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={categoryChartData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={120}
                      label={(entry) => `${entry.name} (${entry.value})`}
                      labelLine={false}
                    >
                      {categoryChartData.map((_entry, index) => (
                        <Cell
                          key={`cat-${index}`}
                          fill={CATEGORY_COLORS[index % CATEGORY_COLORS.length]}
                        />
                      ))}
                    </Pie>
                    <RechartsTooltip
                      formatter={(value: number | string, _name, props) => [
                        `${formatNumber(Number(value))}개 / 재고 ${formatNumber(Number(props.payload?.stock ?? 0))}`,
                        props.payload?.name ?? "",
                      ]}
                    />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} lg={12}>
          <Card
            title="세션 상태 분포"
            extra={
              <Text type="secondary" style={{ fontSize: 12 }}>
                6 status 전체
              </Text>
            }
          >
            <div style={{ width: "100%", height: 320 }}>
              {sessionChartData.every((d) => d.count === 0) ? (
                <Empty
                  description="해당 기간 세션 없음"
                  style={{ paddingTop: 60 }}
                />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={sessionChartData}
                    margin={{ top: 16, right: 24, bottom: 8, left: 8 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                    <XAxis dataKey="statusLabel" tick={{ fontSize: 12 }} />
                    <YAxis
                      tick={{ fontSize: 12 }}
                      allowDecimals={false}
                    />
                    <RechartsTooltip
                      formatter={(value: number | string) =>
                        `${formatNumber(Number(value))}건`
                      }
                    />
                    <Bar dataKey="count" name="건수" radius={[6, 6, 0, 0]}>
                      {sessionChartData.map((entry, index) => (
                        <Cell key={`bar-${index}`} fill={entry.color} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
            <div style={{ marginTop: 8 }}>
              <Space size={6} wrap>
                {sessionChartData.map((d) => (
                  <Tag key={d.statusKey} color={d.color}>
                    {d.statusLabel}: {formatNumber(d.count)}
                  </Tag>
                ))}
              </Space>
            </div>
          </Card>
        </Col>
        <Col xs={24} lg={12}>
          <Card
            title="상위 브랜드 Top 10"
            extra={
              <Text type="secondary" style={{ fontSize: 12 }}>
                재고 기준
              </Text>
            }
          >
            <Table
              columns={brandColumns}
              dataSource={invariant.brand}
              rowKey="brand"
              loading={loadingInvariant}
              size="small"
              pagination={false}
              locale={{ emptyText: "브랜드 데이터 없음" }}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
