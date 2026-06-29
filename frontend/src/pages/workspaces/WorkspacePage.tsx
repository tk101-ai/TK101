import { useNavigate } from "react-router-dom";
import { Button, Card, Space, Tag, Typography } from "antd";
import { ArrowRightOutlined } from "@ant-design/icons";

const { Title, Text, Paragraph } = Typography;

export interface WorkspaceTool {
  title: string;
  desc: string;
  /** ready=기존 도구로 바로 사용 / soon=데이터·API 연동 예정. */
  status: "ready" | "soon";
  /** 사용 가능 도구로 이동할 경로. */
  to?: string;
  actionLabel?: string;
  /** 연동 예정 메모(soon 일 때 보조 설명). */
  note?: string;
}

export interface WorkspacePageProps {
  brand: string;
  subtitle: string;
  tools: WorkspaceTool[];
}

/** 신규 클라이언트 작업공간(테스트) — 계획된 작업을 카드로, 가능한 건 기존 도구로 연결. */
export default function WorkspacePage({ brand, subtitle, tools }: WorkspacePageProps) {
  const navigate = useNavigate();
  return (
    <div style={{ maxWidth: 1100 }}>
      <div style={{ marginBottom: 18 }}>
        <Space align="center" size={10} wrap>
          <Title level={3} style={{ margin: 0 }}>
            {brand}
          </Title>
          <Tag color="purple" bordered={false}>
            테스트 워크스페이스
          </Tag>
        </Space>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          {subtitle}
        </Paragraph>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
          gap: 16,
        }}
      >
        {tools.map((t) => (
          <Card key={t.title} size="small" style={{ height: "100%" }}>
            <Space direction="vertical" size={8} style={{ width: "100%" }}>
              <Space size={8} wrap>
                <Text strong>{t.title}</Text>
                {t.status === "ready" ? (
                  <Tag color="green" bordered={false}>
                    사용 가능
                  </Tag>
                ) : (
                  <Tag color="gold" bordered={false}>
                    준비 중
                  </Tag>
                )}
              </Space>
              <Text type="secondary" style={{ fontSize: 13 }}>
                {t.desc}
              </Text>
              {t.note && (
                <Text type="secondary" style={{ fontSize: 12 }}>
                  ※ {t.note}
                </Text>
              )}
              {t.status === "ready" && t.to ? (
                <Button
                  type="primary"
                  size="small"
                  icon={<ArrowRightOutlined />}
                  onClick={() => navigate(t.to!)}
                  style={{ alignSelf: "flex-start" }}
                >
                  {t.actionLabel ?? "바로 가기"}
                </Button>
              ) : (
                <Button size="small" disabled style={{ alignSelf: "flex-start" }}>
                  데이터·API 연동 예정
                </Button>
              )}
            </Space>
          </Card>
        ))}
      </div>
    </div>
  );
}
