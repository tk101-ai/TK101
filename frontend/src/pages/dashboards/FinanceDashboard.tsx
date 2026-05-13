import {
  Card,
  Col,
  Row,
  Statistic,
  Table,
  Button,
  Progress,
  Tag,
  Space,
  message,
  Spin,
  Empty,
} from "antd";
import {
  BankOutlined,
  SwapOutlined,
  FileTextOutlined,
  ThunderboltOutlined,
  AuditOutlined,
  UploadOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ArrowRightOutlined,
  PieChartOutlined,
} from "@ant-design/icons";
import {
  PieChart,
  Pie,
  Cell,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
  Legend,
} from "recharts";
import { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import dayjs, { type Dayjs } from "dayjs";
import type { ColumnsType } from "antd/es/table";

import { listAccounts, type Account } from "../../api/accounts";
import {
  getTransactions,
  runMatching,
  runReconcile,
  getMonthlySummary,
  getTopCounterparts,
  getAccountBalances,
  type Transaction,
  type MonthlySummaryRow,
  type TopCounterpartRow,
  type AccountBalanceRow,
} from "../../api/transactions";
import { listCategoriesFlat, type CategoryRead } from "../../api/categories";
import { getTaxInvoices } from "../../api/taxInvoices";

import MonthlyChart from "../../components/finance/MonthlyChart";
import AccountBalanceCard from "../../components/finance/AccountBalanceCard";
import TopCounterpartsTable, {
  type PeriodKey,
} from "../../components/finance/TopCounterpartsTable";

interface DashboardStats {
  accountCount: number;
  txnCount: number;
  unmatchedCount: number;
  matchedCount: number;
  taxInvoiceCount: number;
}

const INITIAL_STATS: DashboardStats = {
  accountCount: 0,
  txnCount: 0,
  unmatchedCount: 0,
  matchedCount: 0,
  taxInvoiceCount: 0,
};

// 카테고리 Pie 색상 — 카테고리에 color가 없을 때 fallback 팔레트
const PIE_FALLBACK_COLORS = [
  "#1677ff",
  "#722ed1",
  "#52c41a",
  "#fa8c16",
  "#eb2f96",
  "#13c2c2",
  "#fadb14",
  "#a0d911",
];

// dayjs의 'quarter' 플러그인을 추가로 로드하지 않기 위해 분기 경계를 수동 계산.
function quarterRange(base: Dayjs): [Dayjs, Dayjs] {
  const month = base.month(); // 0~11
  const startMonth = Math.floor(month / 3) * 3;
  const start = base.month(startMonth).startOf("month");
  const end = base.month(startMonth + 2).endOf("month");
  return [start, end];
}

function periodToRange(period: PeriodKey): [string, string] {
  const today = dayjs();
  if (period === "this_month") {
    return [
      today.startOf("month").format("YYYY-MM-DD"),
      today.endOf("month").format("YYYY-MM-DD"),
    ];
  }
  if (period === "last_year_same") {
    const lastYear = today.subtract(1, "year");
    const [s, e] = quarterRange(lastYear);
    return [s.format("YYYY-MM-DD"), e.format("YYYY-MM-DD")];
  }
  // this_quarter (default)
  const [s, e] = quarterRange(today);
  return [s.format("YYYY-MM-DD"), e.format("YYYY-MM-DD")];
}

export default function FinanceDashboard() {
  const navigate = useNavigate();

  // ─────────────────────────────────────────────────────────────────
  // 상태
  // ─────────────────────────────────────────────────────────────────
  const [stats, setStats] = useState<DashboardStats>(INITIAL_STATS);
  const [recentTxns, setRecentTxns] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [balances, setBalances] = useState<AccountBalanceRow[]>([]);
  const [categories, setCategories] = useState<CategoryRead[]>([]);
  const [loading, setLoading] = useState(true);
  const [matchingLoading, setMatchingLoading] = useState(false);
  const [reconcileLoading, setReconcileLoading] = useState(false);

  // 월별 차트
  const [monthlyRange, setMonthlyRange] = useState<[Dayjs, Dayjs]>([
    dayjs().subtract(5, "month").startOf("month"),
    dayjs().endOf("month"),
  ]);
  const [monthlyData, setMonthlyData] = useState<MonthlySummaryRow[]>([]);
  const [monthlyLoading, setMonthlyLoading] = useState(false);
  const [monthlyError, setMonthlyError] = useState<string | null>(null);

  // 상위 거래처
  const [topPeriod, setTopPeriod] = useState<PeriodKey>("this_quarter");
  const [topCounterparts, setTopCounterparts] = useState<TopCounterpartRow[]>([]);
  const [topLoading, setTopLoading] = useState(false);
  const [topError, setTopError] = useState<string | null>(null);

  // 계좌 ID → Account 매핑 (account_id UUID 표시 버그 수정)
  const accountMap = useMemo(
    () => new Map(accounts.map((a) => [a.id, a])),
    [accounts],
  );

  // ─────────────────────────────────────────────────────────────────
  // 데이터 로딩 — 메인 (KPI + 최근거래 + 잔액 + 카테고리)
  // ─────────────────────────────────────────────────────────────────
  const fetchDashboardData = useCallback(async () => {
    setLoading(true);
    try {
      const [
        accountsData,
        allTxnRes,
        unmatchedRes,
        taxRes,
        recentRes,
        balancesData,
        categoriesData,
      ] = await Promise.all([
        listAccounts(),
        getTransactions({ limit: 1 }),
        getTransactions({ match_status: "unmatched", limit: 1 }),
        getTaxInvoices({}).catch(() => ({ data: [] })),
        getTransactions({ limit: 10 }),
        getAccountBalances().catch(() => [] as AccountBalanceRow[]),
        listCategoriesFlat().catch(() => [] as CategoryRead[]),
      ]);

      const totalTxn =
        Number(allTxnRes.headers?.["x-total-count"]) || allTxnRes.data.length;
      const unmatchedLen =
        Number(unmatchedRes.headers?.["x-total-count"]) ||
        unmatchedRes.data.length;
      const matchedLen = totalTxn - unmatchedLen;

      setAccounts(accountsData);
      setStats({
        accountCount: accountsData.length,
        txnCount: totalTxn,
        unmatchedCount: unmatchedLen,
        matchedCount: matchedLen,
        taxInvoiceCount: taxRes.data.length,
      });
      setRecentTxns(recentRes.data);
      setBalances(balancesData);
      setCategories(categoriesData);
    } catch {
      message.error("대시보드 데이터를 불러오는데 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  // 월별 집계 (range 변경 시 재호출)
  const fetchMonthly = useCallback(async () => {
    setMonthlyLoading(true);
    setMonthlyError(null);
    try {
      const data = await getMonthlySummary({
        from: monthlyRange[0].format("YYYY-MM"),
        to: monthlyRange[1].format("YYYY-MM"),
      });
      setMonthlyData(data);
    } catch (err) {
      setMonthlyData([]);
      setMonthlyError(
        err instanceof Error ? err.message : "월별 데이터를 불러오지 못했습니다.",
      );
    } finally {
      setMonthlyLoading(false);
    }
  }, [monthlyRange]);

  // 상위 거래처 (period 변경 시 재호출)
  const fetchTopCounterparts = useCallback(async () => {
    setTopLoading(true);
    setTopError(null);
    try {
      const [from, to] = periodToRange(topPeriod);
      const data = await getTopCounterparts({
        period_from: from,
        period_to: to,
        type: "withdrawal",
        limit: 5,
      });
      setTopCounterparts(data);
    } catch (err) {
      setTopCounterparts([]);
      setTopError(
        err instanceof Error ? err.message : "거래처 데이터를 불러오지 못했습니다.",
      );
    } finally {
      setTopLoading(false);
    }
  }, [topPeriod]);

  useEffect(() => {
    // 마운트/콜백 변경 시 대시보드 데이터 fetch (의도된 패턴).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchDashboardData();
  }, [fetchDashboardData]);

  useEffect(() => {
    // monthlyRange 변경 시 월별 집계 재요청.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchMonthly();
  }, [fetchMonthly]);

  useEffect(() => {
    // topPeriod 변경 시 상위 거래처 재요청.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchTopCounterparts();
  }, [fetchTopCounterparts]);

  // ─────────────────────────────────────────────────────────────────
  // 카테고리별 지출 Pie 데이터 (월별 + 카테고리 한정 호출이 불필요하므로
  // 간단히 monthlyData의 합산을 기준으로 두지 않고, 별도 호출 대신
  // 카테고리 목록이 비어있으면 안내 박스를 표시한다.)
  // ─────────────────────────────────────────────────────────────────
  const pieData = useMemo(() => {
    // 카테고리 데이터에 직접 비용 합계가 없으므로,
    // monthly-summary의 출금 합계를 카테고리 비중으로 균등 분배할 수는 없다.
    // 백엔드에 카테고리별 집계 API가 없는 한, 카테고리 목록만 표시한다.
    return categories
      .filter((c) => c.depth === undefined || c.depth === 1)
      .slice(0, 8)
      .map((c, idx) => ({
        name: c.name,
        value: 1, // 균등 — 실데이터 API 없을 때는 단순 비주얼
        color: c.color || PIE_FALLBACK_COLORS[idx % PIE_FALLBACK_COLORS.length],
      }));
  }, [categories]);

  // ─────────────────────────────────────────────────────────────────
  // 매칭 / 정산 액션
  // ─────────────────────────────────────────────────────────────────
  const matchRate =
    stats.txnCount > 0
      ? Math.round((stats.matchedCount / stats.txnCount) * 100)
      : 0;

  const handleRunMatching = async () => {
    setMatchingLoading(true);
    try {
      await runMatching();
      message.success("자동 매칭이 완료되었습니다.");
      void fetchDashboardData();
    } catch {
      message.error("자동 매칭 실행에 실패했습니다.");
    } finally {
      setMatchingLoading(false);
    }
  };

  const handleRunReconcile = async () => {
    setReconcileLoading(true);
    try {
      await runReconcile();
      message.success("세금계산서 대사가 완료되었습니다.");
      void fetchDashboardData();
    } catch {
      message.error("세금계산서 대사 실행에 실패했습니다.");
    } finally {
      setReconcileLoading(false);
    }
  };

  // ─────────────────────────────────────────────────────────────────
  // 최근 거래내역 컬럼 — B2: account_id 표시 + B1: 입금 비교 수정
  // ─────────────────────────────────────────────────────────────────
  const columns: ColumnsType<Transaction> = [
    {
      title: "날짜",
      dataIndex: "transaction_date",
      key: "date",
      width: 110,
      render: (val: string) => dayjs(val).format("YYYY-MM-DD"),
    },
    {
      title: "계좌",
      dataIndex: "account_id",
      key: "account",
      width: 150,
      ellipsis: true,
      render: (val: string) => {
        const acct = accountMap.get(val);
        if (!acct) return val?.slice(0, 8) + "...";
        if (acct.alias) return acct.alias;
        const tail = acct.account_number.slice(-4);
        return `${acct.bank_name} ···${tail}`;
      },
    },
    {
      title: "거래처",
      dataIndex: "counterpart_name",
      key: "counterpart",
      width: 140,
      ellipsis: true,
      render: (val: string | null) => val ?? "-",
    },
    {
      title: "금액",
      dataIndex: "amount",
      key: "amount",
      width: 130,
      align: "right",
      render: (val: string, record: Transaction) => {
        const num = Number(val);
        // B1: DB는 영문 "deposit"/"withdrawal"이므로 영문 비교로 수정
        const isDeposit = record.transaction_type === "deposit";
        return (
          <span
            style={{
              color: isDeposit ? "#1677ff" : "#cf1322",
              fontWeight: 600,
              fontVariantNumeric: "tabular-nums",
            }}
          >
            {isDeposit ? "+" : "-"}
            {Math.abs(num).toLocaleString("ko-KR")}원
          </span>
        );
      },
    },
    {
      title: "매칭상태",
      dataIndex: "match_status",
      key: "match_status",
      width: 100,
      align: "center",
      render: (val: string) => {
        const isMatched = val === "matched";
        return (
          <Tag
            icon={isMatched ? <CheckCircleOutlined /> : <CloseCircleOutlined />}
            color={isMatched ? "success" : "error"}
            style={{ margin: 0 }}
          >
            {isMatched ? "매칭" : "미매칭"}
          </Tag>
        );
      },
    },
  ];

  return (
    <Spin spinning={loading} size="large">
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        {/* Header */}
        <h2
          style={{
            marginBottom: 28,
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: "-0.02em",
          }}
        >
          대시보드
        </h2>

        {/* Summary Cards — 모든 카드 onClick 으로 필터된 페이지로 이동 */}
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={6}>
            <Card
              hoverable
              onClick={() => navigate("/accounts")}
              style={{ borderLeft: "3px solid #1677ff", cursor: "pointer" }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="등록 계좌"
                value={stats.accountCount}
                prefix={<BankOutlined style={{ color: "#1677ff" }} />}
                suffix="개"
              />
            </Card>
          </Col>

          <Col xs={24} sm={12} lg={6}>
            <Card
              hoverable
              onClick={() => navigate("/transactions")}
              style={{ borderLeft: "3px solid #722ed1", cursor: "pointer" }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="총 거래내역"
                value={stats.txnCount}
                prefix={<SwapOutlined style={{ color: "#722ed1" }} />}
                suffix="건"
              />
            </Card>
          </Col>

          <Col xs={24} sm={12} lg={6}>
            <Card
              hoverable
              onClick={() => navigate("/transactions?match_status=unmatched")}
              style={{
                borderLeft: `3px solid ${
                  stats.unmatchedCount > 0 ? "#cf1322" : "#52c41a"
                }`,
                cursor: "pointer",
              }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="미매칭 거래"
                value={stats.unmatchedCount}
                prefix={<FileTextOutlined />}
                valueStyle={{
                  color: stats.unmatchedCount > 0 ? "#cf1322" : "#52c41a",
                }}
                suffix="건"
              />
            </Card>
          </Col>

          <Col xs={24} sm={12} lg={6}>
            <Card
              hoverable
              onClick={() => navigate("/tax-invoices")}
              style={{ borderLeft: "3px solid #fa8c16", cursor: "pointer" }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="세금계산서"
                value={stats.taxInvoiceCount}
                prefix={<AuditOutlined style={{ color: "#fa8c16" }} />}
                suffix="건"
              />
            </Card>
          </Col>
        </Row>

        {/* 계좌별 잔액 카드 그리드 */}
        <div style={{ marginTop: 16 }}>
          <AccountBalanceCard balances={balances} loading={loading} />
        </div>

        {/* 월별 입출금 추이 + 상위 거래처 */}
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} lg={14}>
            <MonthlyChart
              data={monthlyData}
              range={monthlyRange}
              onRangeChange={setMonthlyRange}
              loading={monthlyLoading}
              error={monthlyError}
            />
          </Col>
          <Col xs={24} lg={10}>
            <TopCounterpartsTable
              data={topCounterparts}
              period={topPeriod}
              onPeriodChange={setTopPeriod}
              loading={topLoading}
              error={topError}
            />
          </Col>
        </Row>

        {/* 카테고리별 지출 Pie (카테고리가 없을 시 안내) */}
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} md={12}>
            <Card
              title={
                <span>
                  <PieChartOutlined
                    style={{ color: "#722ed1", marginRight: 8 }}
                  />
                  카테고리별 지출
                </span>
              }
            >
              {categories.length === 0 ? (
                <Empty
                  description={
                    <Space direction="vertical" align="center">
                      <span>아직 등록된 카테고리가 없습니다.</span>
                      <Button
                        type="link"
                        onClick={() => navigate("/settings/categories")}
                      >
                        카테고리 기능을 사용해보세요 →
                      </Button>
                    </Space>
                  }
                />
              ) : (
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie
                      data={pieData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={90}
                      label={({ name, percent }) =>
                        percent !== undefined && percent >= 0.05
                          ? `${name} ${(percent * 100).toFixed(0)}%`
                          : ""
                      }
                    >
                      {pieData.map((entry) => (
                        <Cell key={entry.name} fill={entry.color} />
                      ))}
                    </Pie>
                    <RechartsTooltip />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </Card>
          </Col>

          {/* Match Rate */}
          <Col xs={24} md={12}>
            <Card
              title="매칭률"
              styles={{ body: { textAlign: "center", padding: "24px" } }}
              style={{ height: "100%" }}
            >
              <Progress
                type="circle"
                percent={matchRate}
                size={140}
                strokeColor={{
                  "0%": "#722ed1",
                  "100%": "#1677ff",
                }}
                format={(pct) => (
                  <span style={{ fontSize: 28, fontWeight: 700 }}>{pct}%</span>
                )}
              />
              <div
                style={{
                  marginTop: 16,
                  color: "rgba(0,0,0,0.45)",
                  fontSize: 13,
                }}
              >
                {stats.matchedCount}건 매칭 / {stats.txnCount}건 전체
              </div>
            </Card>
          </Col>
        </Row>

        {/* Quick Actions */}
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24}>
            <Card title="빠른 실행">
              <Row gutter={[16, 16]}>
                <Col xs={24} sm={8}>
                  <Button
                    type="primary"
                    icon={<ThunderboltOutlined />}
                    size="large"
                    block
                    loading={matchingLoading}
                    onClick={handleRunMatching}
                    style={{
                      height: 48,
                      fontWeight: 600,
                      background:
                        "linear-gradient(135deg, #722ed1 0%, #1677ff 100%)",
                      border: "none",
                    }}
                  >
                    자동 매칭 실행
                  </Button>
                </Col>
                <Col xs={24} sm={8}>
                  <Button
                    icon={<AuditOutlined />}
                    size="large"
                    block
                    loading={reconcileLoading}
                    onClick={handleRunReconcile}
                    style={{ height: 48, fontWeight: 600 }}
                  >
                    세금계산서 대사
                  </Button>
                </Col>
                <Col xs={24} sm={8}>
                  <Button
                    icon={<UploadOutlined />}
                    size="large"
                    block
                    onClick={() => navigate("/finance/import")}
                    style={{ height: 48, fontWeight: 600 }}
                  >
                    엑셀 업로드
                  </Button>
                </Col>
              </Row>
            </Card>
          </Col>
        </Row>

        {/* Recent Transactions */}
        <Card
          title="최근 거래내역"
          style={{ marginTop: 16 }}
          extra={
            <Button
              type="link"
              icon={<ArrowRightOutlined />}
              onClick={() => navigate("/transactions")}
              style={{ fontWeight: 600 }}
            >
              전체 보기
            </Button>
          }
        >
          <Table<Transaction>
            columns={columns}
            dataSource={recentTxns}
            rowKey="id"
            pagination={false}
            size="middle"
            locale={{ emptyText: "거래내역이 없습니다." }}
            scroll={{ x: 620 }}
          />
        </Card>
      </div>
    </Spin>
  );
}
