import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Progress,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Table,
  Typography,
  message,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { type Dayjs } from "dayjs";
import {
  type OverviewOut,
  type SendSuccessRateOut,
  getOverview,
  getSendSuccessRate,
} from "../../api/distribution_dashboard";
import {
  COMPANY_FILTER_OPTIONS,
  DISTRIBUTION_COMPANIES,
  type DistributionCompany,
  listWeeklySummary,
  type WeeklySummaryOut,
} from "../../api/distribution";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;
const { RangePicker } = DatePicker;

/**
 * 신사업유통 대시보드 페이지 (T9 Phase F-D, admin 전용).
 *
 * F-D 단순화: 차트/카테고리 분포 제거 → 회사 4개별 KPI 수치 카드 중심.
 *
 * 영역:
 * 1. 상단 컨트롤: 회사 Select (4 회사 + "전체") + RangePicker + 새로고침.
 * 2. 회사 = "전체" 선택 시:
 *    - 4 회사 합산 KPI 카드 (매입/입금요청/실입금/외상/제품/재고/송신성공률).
 *    - 회사별 비교 Table (4 행 × KPI 컬럼들).
 * 3. 특정 회사 선택 시: 해당 회사 KPI 만 표시.
 *
 * 데이터 소스:
 * - 전사 OverviewOut/SendSuccessRateOut: 기존 dashboard API (회사 필터 미지원 시
 *   클라이언트 측에서 weekly-summary 합산으로 폴백).
 * - 회사별 비교: weekly-summary 응답을 회사별로 그룹핑/합산.
 */

type DateRange = [Dayjs | null, Dayjs | null] | null;
type CompanyChoice = DistributionCompany | "all";

const NUMBER_FORMATTER = new Intl.NumberFormat("ko-KR");

function formatNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return NUMBER_FORMATTER.format(Math.round(value));
}

function formatMoney(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return NUMBER_FORMATTER.format(Math.round(value));
}

function toIsoDate(d: Dayjs | null | undefined): string | undefined {
  if (!d) return undefined;
  return d.format("YYYY-MM-DD");
}

/** 문자열로 들어온 Decimal 합산 — null/NaN 무시. */
function sumDecimalStr(values: (string | null | undefined)[]): number {
  let total = 0;
  for (const v of values) {
    if (v == null || v === "") continue;
    const n = Number(v);
    if (Number.isFinite(n)) total += n;
  }
  return total;
}

interface CompanyKpi {
  company_label: string;
  kr_purchase: number;
  vn_inventory_move: number;
  vn_sales_completed: number;
  deposit_req_total: number;
  account_deposit: number;
  cash_deposit: number;
  outstanding: number; // 입금요청 - (계좌+현금)
  row_count: number;
}

/** WeeklySummaryOut[] → 회사별 합산 KPI. 4 회사 row 는 0 으로라도 항상 생성. */
function aggregateByCompany(rows: WeeklySummaryOut[]): CompanyKpi[] {
  const map = new Map<string, CompanyKpi>();
  for (const company of DISTRIBUTION_COMPANIES) {
    map.set(company, {
      company_label: company,
      kr_purchase: 0,
      vn_inventory_move: 0,
      vn_sales_completed: 0,
      deposit_req_total: 0,
      account_deposit: 0,
      cash_deposit: 0,
      outstanding: 0,
      row_count: 0,
    });
  }
  for (const row of rows) {
    const key = row.company_label;
    let kpi = map.get(key);
    if (!kpi) {
      kpi = {
        company_label: key,
        kr_purchase: 0,
        vn_inventory_move: 0,
        vn_sales_completed: 0,
        deposit_req_total: 0,
        account_deposit: 0,
        cash_deposit: 0,
        outstanding: 0,
        row_count: 0,
      };
      map.set(key, kpi);
    }
    kpi.kr_purchase += Number(row.kr_purchase ?? 0) || 0;
    kpi.vn_inventory_move += Number(row.vn_inventory_move ?? 0) || 0;
    kpi.vn_sales_completed += Number(row.vn_sales_completed ?? 0) || 0;
    kpi.deposit_req_total += sumDecimalStr([
      row.kr_purchase_deposit_req,
      row.vn_inventory_deposit_req,
      row.vn_sales_deposit_req,
    ]);
    kpi.account_deposit += Number(row.account_deposit ?? 0) || 0;
    kpi.cash_deposit += Number(row.cash_deposit ?? 0) || 0;
    kpi.row_count += 1;
  }
  for (const kpi of map.values()) {
    kpi.outstanding =
      kpi.deposit_req_total - (kpi.account_deposit + kpi.cash_deposit);
  }
  return Array.from(map.values());
}

interface DashboardState {
  overview: OverviewOut | null;
  success: SendSuccessRateOut | null;
  weekly: WeeklySummaryOut[];
}

export default function DashboardPage() {
  const [range, setRange] = useState<DateRange>(null);
  const [company, setCompany] = useState<CompanyChoice>("all");
  const [state, setState] = useState<DashboardState>({
    overview: null,
    success: null,
    weekly: [],
  });
  const [loading, setLoading] = useState(false);
  // backend 가 dashboard endpoints 에 company_label 미지원 → 클라이언트 폴백 사용.
  const [fallbackNote, setFallbackNote] = useState<string | null>(null);

  const fromIso = useMemo(() => toIsoDate(range?.[0]), [range]);
  const toIso = useMemo(() => toIsoDate(range?.[1]), [range]);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    setFallbackNote(null);
    try {
      // 1. 전사 KPI (dashboard endpoints). 회사 필터는 클라이언트에서 처리.
      // 2. weekly-summary: 회사 단위 합산용 raw 데이터. company_label 백엔드
      //    에서 지원하면 서버 필터, 미지원이어도 클라이언트 측에서 회사별로
      //    그룹핑 가능 (응답에 company_label 포함).
      const [overview, success, weekly] = await Promise.all([
        getOverview(fromIso, toIso),
        getSendSuccessRate(fromIso, toIso),
        listWeeklySummary({
          from: fromIso,
          to: toIso,
          limit: 500,
          company_label: company === "all" ? undefined : company,
        }),
      ]);
      setState({ overview, success, weekly });
      if (company !== "all") {
        // 특정 회사 선택 시 overview 가 전사 값일 가능성 → 폴백 안내.
        setFallbackNote(
          "전사 KPI 위젯은 dashboard 백엔드의 회사 필터 지원 여부에 따라 전사 합계일 수 있습니다. 회사별 정확한 수치는 아래 비교 테이블을 참고하세요.",
        );
      }
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "대시보드 데이터 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [fromIso, toIso, company]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const handleRangeChange = (next: DateRange) => {
    setRange(next);
  };

  const handleRefresh = () => {
    void fetchAll();
  };

  // ---------------------------------------------------------------------
  // 파생 데이터
  // ---------------------------------------------------------------------

  const byCompany = useMemo(
    () => aggregateByCompany(state.weekly),
    [state.weekly],
  );

  const selectedKpi: CompanyKpi | null = useMemo(() => {
    if (company === "all") return null;
    return byCompany.find((k) => k.company_label === company) ?? null;
  }, [byCompany, company]);

  // 전체(합산) 또는 특정 회사 모두에 사용할 KPI 묶음.
  const headlineKpi = useMemo(() => {
    if (company === "all") {
      // 4 회사 합산은 byCompany 합계로 직접 계산 (overview 가 부정확할 가능성 대비).
      const total = byCompany.reduce<CompanyKpi>(
        (acc, c) => ({
          company_label: "합산",
          kr_purchase: acc.kr_purchase + c.kr_purchase,
          vn_inventory_move: acc.vn_inventory_move + c.vn_inventory_move,
          vn_sales_completed: acc.vn_sales_completed + c.vn_sales_completed,
          deposit_req_total: acc.deposit_req_total + c.deposit_req_total,
          account_deposit: acc.account_deposit + c.account_deposit,
          cash_deposit: acc.cash_deposit + c.cash_deposit,
          outstanding: acc.outstanding + c.outstanding,
          row_count: acc.row_count + c.row_count,
        }),
        {
          company_label: "합산",
          kr_purchase: 0,
          vn_inventory_move: 0,
          vn_sales_completed: 0,
          deposit_req_total: 0,
          account_deposit: 0,
          cash_deposit: 0,
          outstanding: 0,
          row_count: 0,
        },
      );
      return total;
    }
    return selectedKpi;
  }, [company, byCompany, selectedKpi]);

  const overview = state.overview;
  const success = state.success;
  const successPercent = success ? Math.round(success.success_rate * 100) : 0;

  const compareColumns: ColumnsType<CompanyKpi> = [
    {
      title: "회사",
      dataIndex: "company_label",
      width: 120,
      fixed: "left",
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: "KR 매입",
      dataIndex: "kr_purchase",
      width: 140,
      align: "right",
      render: (v: number) => (
        <span style={{ fontFamily: "monospace", fontSize: 13 }}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: "VN 재고이동",
      dataIndex: "vn_inventory_move",
      width: 140,
      align: "right",
      render: (v: number) => (
        <span style={{ fontFamily: "monospace", fontSize: 13 }}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: "VN 매출완료",
      dataIndex: "vn_sales_completed",
      width: 140,
      align: "right",
      render: (v: number) => (
        <span style={{ fontFamily: "monospace", fontSize: 13 }}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: "입금요청 합계",
      dataIndex: "deposit_req_total",
      width: 140,
      align: "right",
      render: (v: number) => (
        <span style={{ fontFamily: "monospace", fontSize: 13 }}>
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: "실 입금",
      key: "actual_deposit",
      width: 140,
      align: "right",
      render: (_: unknown, row: CompanyKpi) => (
        <span style={{ fontFamily: "monospace", fontSize: 13 }}>
          {formatMoney(row.account_deposit + row.cash_deposit)}
        </span>
      ),
    },
    {
      title: "외상 (잔여)",
      dataIndex: "outstanding",
      width: 140,
      align: "right",
      render: (v: number) => (
        <span
          style={{
            fontFamily: "monospace",
            fontSize: 13,
            color: v > 0 ? "#cf1322" : "#52c41a",
            fontWeight: 600,
          }}
        >
          {formatMoney(v)}
        </span>
      ),
    },
    {
      title: "주차 수",
      dataIndex: "row_count",
      width: 90,
      align: "right",
      render: (v: number) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{v}</span>
      ),
    },
  ];

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
            4 개 회사(TK101 · 래더엑스 · 뉴테인핏 · SYBT)의 매입/매출/입금 현황과
            세션 송신 성공률을 한 화면에서 비교합니다. 회사를 "전체" 로 두면 합산
            + 회사별 비교 테이블이 함께 표시됩니다.
          </Paragraph>
        </div>
        <Space wrap>
          <Select<CompanyChoice>
            value={company}
            onChange={(v) => setCompany(v)}
            options={COMPANY_FILTER_OPTIONS}
            style={{ width: 200 }}
          />
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
            loading={loading}
          >
            새로고침
          </Button>
        </Space>
      </div>

      {fallbackNote && (
        <Alert
          type="info"
          showIcon
          message={fallbackNote}
          style={{ marginBottom: 16 }}
          closable
          onClose={() => setFallbackNote(null)}
        />
      )}

      <Spin spinning={loading} tip="KPI 집계 중…">
        {/* 1행: 매입/매출/입금 4 카드 */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="KR 매입"
                value={formatMoney(headlineKpi?.kr_purchase)}
                valueStyle={{ color: "#1677ff" }}
              />
              <Text type="secondary" style={{ fontSize: 11 }}>
                {company === "all" ? "4 회사 합산" : `${company} 단독`}
              </Text>
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="VN 재고이동"
                value={formatMoney(headlineKpi?.vn_inventory_move)}
                valueStyle={{ color: "#13c2c2" }}
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="VN 매출완료"
                value={formatMoney(headlineKpi?.vn_sales_completed)}
                valueStyle={{ color: "#52c41a" }}
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="입금요청 합계"
                value={formatMoney(headlineKpi?.deposit_req_total)}
                valueStyle={{ color: "#fa8c16" }}
              />
            </Card>
          </Col>
        </Row>

        {/* 2행: 실 입금 / 외상 / 제품·재고 / 송신성공률 */}
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="실 입금 (계좌+현금)"
                value={formatMoney(
                  headlineKpi
                    ? headlineKpi.account_deposit + headlineKpi.cash_deposit
                    : 0,
                )}
                valueStyle={{ color: "#52c41a" }}
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="외상 (잔여)"
                value={formatMoney(headlineKpi?.outstanding)}
                valueStyle={{
                  color:
                    (headlineKpi?.outstanding ?? 0) > 0 ? "#cf1322" : "#52c41a",
                }}
              />
            </Card>
          </Col>
          <Col xs={12} md={6}>
            <Card>
              <Statistic
                title="제품 수 / 총 재고"
                value={formatNumber(overview?.product_count)}
                suffix={
                  <Text type="secondary" style={{ fontSize: 13 }}>
                    {" / "}
                    {formatNumber(overview?.total_stock_qty)} 개
                  </Text>
                }
              />
              <Text type="secondary" style={{ fontSize: 11 }}>
                전사 시점 수치
              </Text>
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

      {/* 회사별 비교 — "전체" 선택 시에만 노출 */}
      {company === "all" && (
        <Card
          title="회사별 KPI 비교"
          size="small"
          extra={
            <Text type="secondary" style={{ fontSize: 12 }}>
              주차별 종합 데이터 합산 기준 · 외상 = 입금요청 - 실입금
            </Text>
          }
        >
          <Table
            columns={compareColumns}
            dataSource={byCompany}
            rowKey="company_label"
            loading={loading}
            size="middle"
            scroll={{ x: 1100 }}
            pagination={false}
            locale={{ emptyText: "회사별 집계 데이터 없음" }}
          />
        </Card>
      )}
    </div>
  );
}
