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
} from "@ant-design/icons";
import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { getAccounts } from "../api/accounts";
import { getTransactions, runMatching, runReconcile } from "../api/transactions";
import type { Transaction } from "../api/transactions";
import { getTaxInvoices } from "../api/taxInvoices";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";

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

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats>(INITIAL_STATS);
  const [recentTxns, setRecentTxns] = useState<Transaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [matchingLoading, setMatchingLoading] = useState(false);
  const [reconcileLoading, setReconcileLoading] = useState(false);
  const navigate = useNavigate();

  const fetchDashboardData = useCallback(async () => {
    setLoading(true);
    try {
      // TODO: replace with a dedicated /api/transactions/count endpoint
      // that returns { total, unmatched } to avoid fetching records just for counts.
      // For now we fetch limit:1 and read the X-Total-Count header when available.
      const [accountsRes, allTxnRes, unmatchedRes, taxRes, recentRes] =
        await Promise.all([
          getAccounts(),
          getTransactions({ limit: 1 }),
          getTransactions({ match_status: "unmatched", limit: 1 }),
          getTaxInvoices({}),
          getTransactions({ limit: 10 }),
        ]);

      const totalTxn =
        Number(allTxnRes.headers?.["x-total-count"]) ||
        allTxnRes.data.length;
      const unmatchedLen =
        Number(unmatchedRes.headers?.["x-total-count"]) ||
        unmatchedRes.data.length;
      const matchedLen = totalTxn - unmatchedLen;

      setStats({
        accountCount: accountsRes.data.length,
        txnCount: totalTxn,
        unmatchedCount: unmatchedLen,
        matchedCount: matchedLen,
        taxInvoiceCount: taxRes.data.length,
      });
      setRecentTxns(recentRes.data);
    } catch {
      message.error("대시보드 데이터를 불러오는데 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDashboardData();
  }, [fetchDashboardData]);

  const matchRate =
    stats.txnCount > 0
      ? Math.round((stats.matchedCount / stats.txnCount) * 100)
      : 0;

  const handleRunMatching = async () => {
    setMatchingLoading(true);
    try {
      await runMatching();
      message.success("자동 매칭이 완료되었습니다.");
      fetchDashboardData();
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
      fetchDashboardData();
    } catch {
      message.error("세금계산서 대사 실행에 실패했습니다.");
    } finally {
      setReconcileLoading(false);
    }
  };

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
      width: 100,
      ellipsis: true,
      render: (val: string) => val?.slice(0, 8) + "...",
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
        const isDeposit = record.transaction_type === "입금";
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

        {/* Summary Cards */}
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={6}>
            <Card
              hoverable
              style={{ borderLeft: "3px solid #1677ff" }}
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
              style={{ borderLeft: "3px solid #722ed1" }}
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
              style={{
                borderLeft: `3px solid ${stats.unmatchedCount > 0 ? "#cf1322" : "#52c41a"}`,
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
              style={{ borderLeft: "3px solid #fa8c16" }}
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

        {/* Match Rate + Quick Actions Row */}
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          {/* Match Rate */}
          <Col xs={24} md={8}>
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
                  <span style={{ fontSize: 28, fontWeight: 700 }}>
                    {pct}%
                  </span>
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

          {/* Quick Actions */}
          <Col xs={24} md={16}>
            <Card title="빠른 실행" style={{ height: "100%" }}>
              <Space
                direction="vertical"
                size="middle"
                style={{ width: "100%" }}
              >
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
                    background: "linear-gradient(135deg, #722ed1 0%, #1677ff 100%)",
                    border: "none",
                  }}
                >
                  자동 매칭 실행
                </Button>

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

                <Button
                  icon={<UploadOutlined />}
                  size="large"
                  block
                  onClick={() => navigate("/transactions")}
                  style={{ height: 48, fontWeight: 600 }}
                >
                  엑셀 업로드
                </Button>
              </Space>
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
            scroll={{ x: 580 }}
          />
        </Card>
      </div>
    </Spin>
  );
}
