import { Card, Col, Row, Space, Statistic, Typography } from "antd";
import type { CompanyChoice } from "./types";
import type { GrandTotal } from "./useProducts";

const { Text } = Typography;

interface GrandTotalCardsProps {
  grandTotal: GrandTotal;
  company: CompanyChoice;
}

export function GrandTotalCards({ grandTotal, company }: GrandTotalCardsProps) {
  return (
    <Row gutter={[12, 12]} style={{ marginBottom: 16 }}>
      <Col xs={12} md={3}>
        <Card size="small">
          <Statistic
            title={
              <Space size={4}>
                <Text>총 제품 수</Text>
                <Text type="secondary" style={{ fontSize: 11 }}>
                  {company === "all" ? "(전체)" : `(${company})`}
                </Text>
              </Space>
            }
            value={grandTotal.count}
            suffix="건"
          />
        </Card>
      </Col>
      <Col xs={12} md={3}>
        <Card size="small">
          <Statistic
            title="총 매입수량"
            value={grandTotal.totalPurchaseQty}
            suffix="개"
            valueStyle={{ color: "#1677ff" }}
          />
        </Card>
      </Col>
      <Col xs={12} md={3}>
        <Card size="small">
          <Statistic
            title="총 국내재고"
            value={grandTotal.totalStockQty}
            suffix="개"
            valueStyle={{ color: "#52c41a" }}
          />
        </Card>
      </Col>
      <Col xs={12} md={3}>
        <Card size="small">
          <Statistic
            title="VN 재고이동"
            value={grandTotal.totalVnInventoryMoveQty}
            suffix="개"
            valueStyle={{ color: "#722ed1" }}
          />
        </Card>
      </Col>
      <Col xs={12} md={3}>
        <Card size="small">
          <Statistic
            title="VN 매출완료"
            value={grandTotal.totalVnSalesCompletedQty}
            suffix="개"
            valueStyle={{ color: "#fa8c16" }}
          />
        </Card>
      </Col>
      <Col xs={12} md={3}>
        <Card size="small">
          <Statistic
            title="VN 현지재고"
            value={grandTotal.totalVnLocalStockQty}
            suffix="개"
            valueStyle={{ color: "#13c2c2" }}
          />
        </Card>
      </Col>
      <Col xs={24} md={6}>
        <Card size="small">
          <Statistic
            title="총 매입금액 (KRW)"
            value={grandTotal.totalPurchasePrice}
            precision={0}
            groupSeparator=","
          />
        </Card>
      </Col>
    </Row>
  );
}
