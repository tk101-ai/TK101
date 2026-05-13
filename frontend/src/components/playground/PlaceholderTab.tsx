import { Empty, Typography } from "antd";

const { Title, Paragraph } = Typography;

interface PlaceholderTabProps {
  title: string;
  description: string;
}

/**
 * Image / Video Gen 탭 placeholder (Phase 4 / Phase 5에서 본격 구현).
 */
export default function PlaceholderTab({ title, description }: PlaceholderTabProps) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: 480,
        padding: 24,
      }}
    >
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description={
          <div style={{ maxWidth: 420, textAlign: "center" }}>
            <Title level={4} style={{ margin: 0 }}>
              {title}
            </Title>
            <Paragraph type="secondary" style={{ marginTop: 8 }}>
              {description}
            </Paragraph>
          </div>
        }
      />
    </div>
  );
}
