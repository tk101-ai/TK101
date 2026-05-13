import { Card, Col, Row, Empty, Tag, Tooltip } from "antd";
import { BankOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import dayjs from "dayjs";
import type { AccountBalanceRow } from "../../api/transactions";

/**
 * 계좌별 잔액 카드 그리드 (재무 대시보드 — Wave 3 FE-C).
 *
 * 각 카드는 hoverable + onClick → /transactions?account_id={id} 로 이동.
 * 잔액이 null 이거나 NaN 이면 "—" 표시.
 */

interface AccountBalanceCardProps {
  balances: AccountBalanceRow[];
  loading?: boolean;
}

function formatBalance(currency: string, value: string | null): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = Number(value);
  if (!Number.isFinite(num)) return "—";
  return `${currency} ${num.toLocaleString("ko-KR", {
    maximumFractionDigits: currency === "KRW" ? 0 : 2,
  })}`;
}

function formatLastDate(row: AccountBalanceRow): string {
  const ts = row.last_transaction_date ?? row.last_synced_at;
  if (!ts) return "—";
  return dayjs(ts).format("YYYY-MM-DD");
}

function tail4(accountNumber: string): string {
  return accountNumber.length > 4 ? accountNumber.slice(-4) : accountNumber;
}

export default function AccountBalanceCard({
  balances,
  loading,
}: AccountBalanceCardProps) {
  const navigate = useNavigate();

  if (!loading && balances.length === 0) {
    return (
      <Card title="계좌별 잔액">
        <Empty description="등록된 계좌가 없습니다." />
      </Card>
    );
  }

  return (
    <Card
      title={
        <span>
          <BankOutlined style={{ color: "#1677ff", marginRight: 8 }} />
          계좌별 잔액
        </span>
      }
      loading={loading}
    >
      <Row gutter={[16, 16]}>
        {balances.map((b) => (
          <Col key={b.account_id} xs={24} sm={12} md={12} lg={8} xl={6}>
            <Card
              hoverable
              size="small"
              onClick={() =>
                navigate(`/transactions?account_id=${b.account_id}`)
              }
              styles={{ body: { padding: "16px 18px" } }}
              style={{
                borderLeft: "3px solid #1677ff",
                cursor: "pointer",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: 8,
                }}
              >
                <span style={{ fontWeight: 600, fontSize: 14 }}>
                  {b.bank_name}
                </span>
                {b.account_type && (
                  <Tag color="blue" style={{ margin: 0 }}>
                    {b.account_type}
                  </Tag>
                )}
              </div>
              <Tooltip title={b.account_number}>
                <div
                  style={{
                    fontSize: 12,
                    color: "rgba(0,0,0,0.45)",
                    marginBottom: 12,
                  }}
                >
                  ···{tail4(b.account_number)}
                </div>
              </Tooltip>
              <div
                style={{
                  fontSize: 18,
                  fontWeight: 700,
                  fontVariantNumeric: "tabular-nums",
                  color: "#262626",
                  marginBottom: 6,
                }}
              >
                {formatBalance(b.currency, b.current_balance)}
              </div>
              <div style={{ fontSize: 11, color: "rgba(0,0,0,0.45)" }}>
                최근 거래일: {formatLastDate(b)}
              </div>
            </Card>
          </Col>
        ))}
      </Row>
    </Card>
  );
}
