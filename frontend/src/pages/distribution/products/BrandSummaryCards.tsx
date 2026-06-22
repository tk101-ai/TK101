import { Card, Space, Tag, Typography } from "antd";
import { getBrandColor } from "./colors";
import { formatNumber } from "./format";
import type { CompanyChoice } from "./types";
import type { BrandStat } from "./useProducts";

const { Text } = Typography;

interface BrandSummaryCardsProps {
  brandStats: BrandStat[];
  company: CompanyChoice;
}

export function BrandSummaryCards({
  brandStats,
  company,
}: BrandSummaryCardsProps) {
  if (brandStats.length === 0) return null;

  return (
    <Card
      size="small"
      style={{ marginBottom: 16 }}
      title={
        <Space>
          <Text strong>브랜드별 요약</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {company === "all" ? "전체 회사" : company}
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
        {brandStats.map((s) => (
          <div
            key={s.brand}
            style={{
              padding: "14px 16px",
              background: "#fafafa",
              border: "1px solid #f0f0f0",
              borderRadius: 8,
              display: "flex",
              flexDirection: "column",
              gap: 10,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: 8,
              }}
            >
              <Text
                strong
                style={{
                  fontSize: 18,
                  letterSpacing: "-0.02em",
                  lineHeight: 1.2,
                }}
              >
                {s.brand}
              </Text>
              <Tag color={getBrandColor(s.brand)} style={{ margin: 0 }}>
                {s.count}개
              </Tag>
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(5, 1fr)",
                gap: 6,
              }}
            >
              <div>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  매입
                </Text>
                <div
                  style={{
                    fontSize: 14,
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
                    fontSize: 14,
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
                    fontSize: 14,
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
                    fontSize: 14,
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
                    fontSize: 14,
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
        ))}
      </div>
    </Card>
  );
}
