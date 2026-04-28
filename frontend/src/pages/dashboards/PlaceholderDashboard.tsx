import { Alert, Card, Col, Row, Tag } from "antd";

interface WidgetSlot {
  title: string;
  description: string;
}

interface PlaceholderDashboardProps {
  departmentLabel: string;
  widgets: WidgetSlot[];
}

export default function PlaceholderDashboard({
  departmentLabel,
  widgets,
}: PlaceholderDashboardProps) {
  return (
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
        {`${departmentLabel} 대시보드`}
      </h2>

      {/* Info banner */}
      <Alert
        type="info"
        showIcon
        message="부서별 위젯이 곧 추가됩니다."
        style={{ marginBottom: 24 }}
      />

      {/* Widget placeholder grid */}
      <Row gutter={[16, 16]}>
        {widgets.map((widget) => (
          <Col xs={24} sm={12} lg={8} key={widget.title}>
            <Card
              hoverable
              style={{ borderLeft: "3px solid #fa8c16", height: "100%" }}
              styles={{ body: { padding: "20px 24px" } }}
              title={widget.title}
              extra={<Tag color="orange">준비 중</Tag>}
            >
              <div style={{ color: "rgba(0,0,0,0.55)", fontSize: 13, lineHeight: 1.6 }}>
                {widget.description}
              </div>
            </Card>
          </Col>
        ))}
      </Row>
    </div>
  );
}
