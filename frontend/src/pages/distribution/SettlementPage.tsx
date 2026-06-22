import { type CSSProperties, useCallback, useEffect, useMemo, useState } from "react";
import {
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
  Tag,
  Typography,
  message,
} from "antd";
import { ReloadOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type { Dayjs } from "dayjs";
import {
  type ByCompanyItem,
  type CashFlowItem,
  type SettlementSummary,
  getByCompany,
  getCashFlow,
  getSettlementSummary,
  listSettlementCompanies,
} from "../../api/distribution_settlement";
import { extractErrorDetail } from "../../utils/errorUtils";
import { formatNumber, toIsoDate } from "../../utils/format";

const { Title, Paragraph, Text } = Typography;
const { RangePicker } = DatePicker;

/**
 * 신사업유통 정산 페이지 (T9 Phase F-C, admin 전용).
 *
 * 엑셀 종합관리시트 기반 자금 흐름 시각화:
 * 1. 상단 필터 — 회사 Select + 기간 RangePicker
 * 2. KPI 카드 5개 — 매입 / 입금요청 / 실입금 / 외상잔고 / 이행률
 * 3. 회사별 비교 Table (by-company) — 4개 회사 모두 표시
 * 4. 주차별 정산 Table (cash-flow) — 모든 컬럼 + Progress(이행률)
 *
 * 의미:
 * - 매입 = kr_purchase + vn_inventory_move + vn_sales_completed
 * - 입금요청 = KR매입×40% + VN재고×30% + VN매출×30% (자동계산)
 * - 실 입금 = account_deposit + cash_deposit
 * - 외상잔고 = kr_purchase - 실 입금 (시트 정의)
 * - 이행률 = 실 입금 / 입금요청 (0.0~1.0)
 */

type DateRange = [Dayjs | null, Dayjs | null] | null;

function ratioPercent(rate: number | null | undefined): number {
  if (rate == null || !Number.isFinite(rate)) return 0;
  return Math.round(rate * 100);
}

// 금액 표시 — 천단위 monospace 우측정렬.
const moneyCellStyle: CSSProperties = {
  fontFamily:
    "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
  fontSize: 13,
  fontVariantNumeric: "tabular-nums",
};

function MoneyCell({ value }: { value: number | null | undefined }) {
  return <span style={moneyCellStyle}>{formatNumber(value)}</span>;
}

// 회사별 비교 테이블 컬럼.
function buildByCompanyColumns(): ColumnsType<ByCompanyItem> {
  return [
    {
      title: "회사",
      dataIndex: "company_label",
      width: 140,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: "주차 수",
      dataIndex: "period_count",
      width: 90,
      align: "right" as const,
      render: (v: number) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {formatNumber(v)}
        </span>
      ),
    },
    {
      title: "KR 매입",
      dataIndex: "total_kr_purchase",
      align: "right" as const,
      render: (v: number) => <MoneyCell value={v} />,
    },
    {
      title: "입금요청",
      dataIndex: "total_deposit_req",
      align: "right" as const,
      render: (v: number) => <MoneyCell value={v} />,
    },
    {
      title: "실 입금",
      dataIndex: "total_deposit_received",
      align: "right" as const,
      render: (v: number) => <MoneyCell value={v} />,
    },
    {
      title: "외상잔고",
      dataIndex: "total_outstanding",
      align: "right" as const,
      render: (v: number) => (
        <span style={{ ...moneyCellStyle, color: v > 0 ? "#cf1322" : "#52c41a" }}>
          {formatNumber(v)}
        </span>
      ),
    },
    {
      title: "이행률",
      dataIndex: "fulfillment_rate",
      width: 180,
      render: (v: number) => (
        <Progress
          percent={ratioPercent(v)}
          size="small"
          strokeColor="#52c41a"
          format={(p) => `${p ?? 0}%`}
        />
      ),
    },
  ];
}

// 주차별 cash-flow 컬럼.
function buildCashFlowColumns(): ColumnsType<CashFlowItem> {
  return [
    {
      title: "주차",
      dataIndex: "period_label",
      width: 110,
      fixed: "left" as const,
      render: (v: string) => <Text strong>{v}</Text>,
    },
    {
      title: "회사",
      dataIndex: "company_label",
      width: 110,
      fixed: "left" as const,
      render: (v: string) => <Tag color="blue">{v}</Tag>,
    },
    {
      title: "기간",
      key: "period_range",
      width: 200,
      render: (_: unknown, row: CashFlowItem) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {row.period_start} ~ {row.period_end}
        </Text>
      ),
    },
    {
      title: "KR 매입",
      dataIndex: "kr_purchase",
      align: "right" as const,
      width: 140,
      render: (v: number) => <MoneyCell value={v} />,
    },
    {
      title: "VN 재고이동",
      dataIndex: "vn_inventory_move",
      align: "right" as const,
      width: 140,
      render: (v: number) => <MoneyCell value={v} />,
    },
    {
      title: "VN 매출완료",
      dataIndex: "vn_sales_completed",
      align: "right" as const,
      width: 140,
      render: (v: number) => <MoneyCell value={v} />,
    },
    {
      title: "KR매입 요청(40%)",
      dataIndex: "kr_purchase_deposit_req",
      align: "right" as const,
      width: 150,
      render: (v: number) => <MoneyCell value={v} />,
    },
    {
      title: "VN재고 요청(30%)",
      dataIndex: "vn_inventory_deposit_req",
      align: "right" as const,
      width: 150,
      render: (v: number) => <MoneyCell value={v} />,
    },
    {
      title: "VN매출 요청(30%)",
      dataIndex: "vn_sales_deposit_req",
      align: "right" as const,
      width: 150,
      render: (v: number) => <MoneyCell value={v} />,
    },
    {
      title: "입금요청 합계",
      dataIndex: "deposit_req_total",
      align: "right" as const,
      width: 150,
      render: (v: number) => (
        <span style={{ ...moneyCellStyle, color: "#fa8c16", fontWeight: 600 }}>
          {formatNumber(v)}
        </span>
      ),
    },
    {
      title: "계좌 입금",
      dataIndex: "account_deposit",
      align: "right" as const,
      width: 130,
      render: (v: number) => <MoneyCell value={v} />,
    },
    {
      title: "현금 입금",
      dataIndex: "cash_deposit",
      align: "right" as const,
      width: 130,
      render: (v: number) => <MoneyCell value={v} />,
    },
    {
      title: "실 입금 합계",
      dataIndex: "deposit_total",
      align: "right" as const,
      width: 150,
      render: (v: number) => (
        <span style={{ ...moneyCellStyle, color: "#1677ff", fontWeight: 600 }}>
          {formatNumber(v)}
        </span>
      ),
    },
    {
      title: "외상잔고",
      dataIndex: "outstanding_balance",
      align: "right" as const,
      width: 140,
      render: (v: number) => (
        <span
          style={{
            ...moneyCellStyle,
            color: v > 0 ? "#cf1322" : "#52c41a",
            fontWeight: 600,
          }}
        >
          {formatNumber(v)}
        </span>
      ),
    },
    {
      title: "이행률",
      dataIndex: "fulfillment_rate",
      width: 160,
      render: (v: number) => (
        <Progress
          percent={ratioPercent(v)}
          size="small"
          strokeColor={v >= 1 ? "#52c41a" : v >= 0.7 ? "#1677ff" : "#faad14"}
          format={(p) => `${p ?? 0}%`}
        />
      ),
    },
  ];
}

export default function SettlementPage() {
  const [companies, setCompanies] = useState<string[]>([]);
  const [selectedCompany, setSelectedCompany] = useState<string | undefined>(
    undefined,
  );
  const [range, setRange] = useState<DateRange>(null);
  const [summary, setSummary] = useState<SettlementSummary | null>(null);
  const [byCompany, setByCompany] = useState<ByCompanyItem[]>([]);
  const [cashFlow, setCashFlow] = useState<CashFlowItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingCompanies, setLoadingCompanies] = useState(false);

  const fromIso = useMemo(() => toIsoDate(range?.[0]), [range]);
  const toIso = useMemo(() => toIsoDate(range?.[1]), [range]);

  const fetchCompanies = useCallback(async () => {
    setLoadingCompanies(true);
    try {
      const items = await listSettlementCompanies();
      setCompanies(items);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "회사 목록 조회 실패"));
    } finally {
      setLoadingCompanies(false);
    }
  }, []);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const params = {
        from: fromIso,
        to: toIso,
        company_label: selectedCompany,
      };
      const [summaryRes, byCompanyRes, cashFlowRes] = await Promise.all([
        getSettlementSummary(params),
        getByCompany({ from: fromIso, to: toIso }),
        getCashFlow(params),
      ]);
      setSummary(summaryRes);
      setByCompany(byCompanyRes);
      setCashFlow(cashFlowRes);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "정산 데이터 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [fromIso, toIso, selectedCompany]);

  useEffect(() => {
    void fetchCompanies();
  }, [fetchCompanies]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const handleRefresh = () => {
    void fetchCompanies();
    void fetchAll();
  };

  const byCompanyColumns = useMemo(() => buildByCompanyColumns(), []);
  const cashFlowColumns = useMemo(() => buildCashFlowColumns(), []);

  const fulfillmentPercent = summary
    ? ratioPercent(summary.fulfillment_rate)
    : 0;

  return (
    <div style={{ maxWidth: 1920 }}>
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
            정산 / 자금 흐름
          </Title>
          <Paragraph type="secondary" style={{ margin: "4px 0 0", maxWidth: 720 }}>
            엑셀 종합관리시트의 주차별 자금 흐름을 회사별·기간별로 집계합니다.
            매입(KR/VN) → 입금요청(40%/30%/30%) → 실 입금(계좌+현금) → 외상잔고
            흐름을 추적합니다. 이행률 = 실 입금 / 입금요청.
          </Paragraph>
        </div>
        <Space wrap>
          <Select
            placeholder="회사 (전체)"
            value={selectedCompany}
            onChange={(v) => setSelectedCompany(v)}
            allowClear
            loading={loadingCompanies}
            style={{ width: 180 }}
            options={companies.map((c) => ({ value: c, label: c }))}
          />
          <RangePicker
            value={range ?? undefined}
            onChange={(next) => setRange(next as DateRange)}
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

      <Spin spinning={loading} tip="정산 데이터 집계 중...">
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          <Col xs={24} sm={12} md={8} lg={5}>
            <Card>
              <Statistic
                title="총 매입 (KR)"
                value={formatNumber(summary?.total_kr_purchase)}
                valueStyle={{ color: "#1677ff" }}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                VN재고 {formatNumber(summary?.total_vn_inventory_move)} / VN매출{" "}
                {formatNumber(summary?.total_vn_sales)}
              </Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={8} lg={5}>
            <Card>
              <Statistic
                title="입금요청 합계"
                value={formatNumber(summary?.total_deposit_req)}
                valueStyle={{ color: "#fa8c16" }}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                40% + 30% + 30% 자동계산
              </Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={8} lg={5}>
            <Card>
              <Statistic
                title="실 입금 합계"
                value={formatNumber(summary?.total_deposit_received)}
                valueStyle={{ color: "#52c41a" }}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                계좌 + 현금 입금
              </Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={8} lg={5}>
            <Card>
              <Statistic
                title="외상잔고"
                value={formatNumber(summary?.total_outstanding)}
                valueStyle={{
                  color:
                    summary && summary.total_outstanding > 0
                      ? "#cf1322"
                      : "#52c41a",
                }}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                KR매입 − 실 입금
              </Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={8} lg={4}>
            <Card>
              <Space direction="vertical" size={4} style={{ width: "100%" }}>
                <Text type="secondary" style={{ fontSize: 14 }}>
                  이행률
                </Text>
                <Progress
                  percent={fulfillmentPercent}
                  size={[160, 12]}
                  strokeColor={
                    fulfillmentPercent >= 100
                      ? "#52c41a"
                      : fulfillmentPercent >= 70
                        ? "#1677ff"
                        : "#faad14"
                  }
                  format={(p) => `${p ?? 0}%`}
                />
                <Text type="secondary" style={{ fontSize: 12 }}>
                  {summary
                    ? `${summary.period_count}주차 / ${summary.company_count}개사`
                    : "—"}
                  {summary?.latest_period_label
                    ? ` · 최신 ${summary.latest_period_label}`
                    : ""}
                </Text>
              </Space>
            </Card>
          </Col>
        </Row>
      </Spin>

      <Card
        title="회사별 비교"
        style={{ marginBottom: 16 }}
        extra={
          <Text type="secondary" style={{ fontSize: 12 }}>
            기간 필터 적용 · 회사 필터 무관 (4개사 전체)
          </Text>
        }
      >
        <Table
          columns={byCompanyColumns}
          dataSource={byCompany}
          rowKey="company_label"
          size="small"
          pagination={false}
          loading={loading}
          locale={{ emptyText: "회사 데이터 없음" }}
        />
      </Card>

      <Card
        title="주차별 정산"
        extra={
          <Text type="secondary" style={{ fontSize: 12 }}>
            period_start 오름차순 · {cashFlow.length}개 행
          </Text>
        }
      >
        <Table
          columns={cashFlowColumns}
          dataSource={cashFlow}
          rowKey={(row) =>
            `${row.company_label}-${row.period_start}-${row.period_end}`
          }
          size="small"
          loading={loading}
          scroll={{ x: 1900 }}
          pagination={{
            pageSize: 20,
            showSizeChanger: true,
            pageSizeOptions: ["10", "20", "50", "100"],
          }}
          locale={{
            emptyText:
              "해당 조건의 정산 데이터가 없습니다. 주차별 종합 데이터를 먼저 업로드하세요.",
          }}
          summary={(rows) => {
            if (rows.length === 0) return null;
            const total = {
              kr_purchase: 0,
              vn_inventory_move: 0,
              vn_sales_completed: 0,
              kr_purchase_deposit_req: 0,
              vn_inventory_deposit_req: 0,
              vn_sales_deposit_req: 0,
              deposit_req_total: 0,
              account_deposit: 0,
              cash_deposit: 0,
              deposit_total: 0,
              outstanding_balance: 0,
            };
            for (const row of rows) {
              total.kr_purchase += row.kr_purchase;
              total.vn_inventory_move += row.vn_inventory_move;
              total.vn_sales_completed += row.vn_sales_completed;
              total.kr_purchase_deposit_req += row.kr_purchase_deposit_req;
              total.vn_inventory_deposit_req += row.vn_inventory_deposit_req;
              total.vn_sales_deposit_req += row.vn_sales_deposit_req;
              total.deposit_req_total += row.deposit_req_total;
              total.account_deposit += row.account_deposit;
              total.cash_deposit += row.cash_deposit;
              total.deposit_total += row.deposit_total;
              total.outstanding_balance += row.outstanding_balance;
            }
            const overallRate =
              total.deposit_req_total > 0
                ? total.deposit_total / total.deposit_req_total
                : 0;
            return (
              <Table.Summary fixed>
                <Table.Summary.Row style={{ background: "#fafafa" }}>
                  <Table.Summary.Cell index={0} colSpan={3}>
                    <Text strong>현재 페이지 합계</Text>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={3} align="right">
                    <MoneyCell value={total.kr_purchase} />
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={4} align="right">
                    <MoneyCell value={total.vn_inventory_move} />
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={5} align="right">
                    <MoneyCell value={total.vn_sales_completed} />
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={6} align="right">
                    <MoneyCell value={total.kr_purchase_deposit_req} />
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={7} align="right">
                    <MoneyCell value={total.vn_inventory_deposit_req} />
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={8} align="right">
                    <MoneyCell value={total.vn_sales_deposit_req} />
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={9} align="right">
                    <span
                      style={{ ...moneyCellStyle, color: "#fa8c16", fontWeight: 600 }}
                    >
                      {formatNumber(total.deposit_req_total)}
                    </span>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={10} align="right">
                    <MoneyCell value={total.account_deposit} />
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={11} align="right">
                    <MoneyCell value={total.cash_deposit} />
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={12} align="right">
                    <span
                      style={{ ...moneyCellStyle, color: "#1677ff", fontWeight: 600 }}
                    >
                      {formatNumber(total.deposit_total)}
                    </span>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={13} align="right">
                    <span
                      style={{
                        ...moneyCellStyle,
                        color: total.outstanding_balance > 0 ? "#cf1322" : "#52c41a",
                        fontWeight: 600,
                      }}
                    >
                      {formatNumber(total.outstanding_balance)}
                    </span>
                  </Table.Summary.Cell>
                  <Table.Summary.Cell index={14}>
                    <Progress
                      percent={ratioPercent(overallRate)}
                      size="small"
                      strokeColor="#52c41a"
                      format={(p) => `${p ?? 0}%`}
                    />
                  </Table.Summary.Cell>
                </Table.Summary.Row>
              </Table.Summary>
            );
          }}
        />
      </Card>
    </div>
  );
}
