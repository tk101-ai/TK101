import { Card, Space, Tag, Typography } from "antd";
import { formatNumber } from "./format";
import type { CompanyChoice } from "./types";
import type { CompanyStat } from "./useProducts";

const { Text } = Typography;

interface CompanySummaryCardsProps {
  companyStats: CompanyStat[];
  company: CompanyChoice;
  onSelectCompany: (label: CompanyChoice) => void;
}

export function CompanySummaryCards({
  companyStats,
  company,
  onSelectCompany,
}: CompanySummaryCardsProps) {
  return (
    <Card
      size="small"
      style={{ marginBottom: 16 }}
      title={
        <Space>
          <Text strong>회사별 재고 요약</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            (4 업체 비교 — 항상 전체 데이터 기준)
          </Text>
        </Space>
      }
    >
      <div
        style={{
          display: "grid",
          gap: 12,
          gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
        }}
      >
        {companyStats.map((s) => {
          const isSelected = company === s.label;
          return (
            <div
              key={s.label}
              onClick={() => onSelectCompany(s.label as CompanyChoice)}
              style={{
                padding: "12px 14px",
                background: isSelected ? "#e6f4ff" : "#fafafa",
                border: `1px solid ${isSelected ? "#1677ff" : "#f0f0f0"}`,
                borderRadius: 8,
                cursor: "pointer",
                transition: "all 0.15s",
                display: "flex",
                flexDirection: "column",
                gap: 8,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <Text strong style={{ fontSize: 15 }}>
                  {s.label}
                </Text>
                <Tag color="geekblue" style={{ margin: 0 }}>
                  {s.count}건
                </Tag>
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(5, 1fr)",
                  gap: 4,
                }}
              >
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    매입
                  </Text>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      fontVariantNumeric: "tabular-nums",
                      color: "#1677ff",
                    }}
                  >
                    {formatNumber(s.totalPurchaseQty)}
                  </div>
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    국내
                  </Text>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      fontVariantNumeric: "tabular-nums",
                      color: "#52c41a",
                    }}
                  >
                    {formatNumber(s.totalStockQty)}
                  </div>
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    VN이동
                  </Text>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      fontVariantNumeric: "tabular-nums",
                      color: "#722ed1",
                    }}
                  >
                    {formatNumber(s.totalVnInventoryMoveQty)}
                  </div>
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    VN매출
                  </Text>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      fontVariantNumeric: "tabular-nums",
                      color: "#fa8c16",
                    }}
                  >
                    {formatNumber(s.totalVnSalesCompletedQty)}
                  </div>
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>
                    VN재고
                  </Text>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      fontVariantNumeric: "tabular-nums",
                      color: "#13c2c2",
                    }}
                  >
                    {formatNumber(s.totalVnLocalStockQty)}
                  </div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
}
