import { Card, Col, Row, Statistic } from "antd";
import { ArrowUpOutlined, ArrowDownOutlined } from "@ant-design/icons";
import {
  LANGUAGE_LABELS,
  PLATFORM_LABELS,
  formatNumber,
  formatPercent,
} from "./constants";
import type { GrowthCard } from "./types";

interface GrowthCardsProps {
  growthData: GrowthCard[];
}

export default function GrowthCards({ growthData }: GrowthCardsProps) {
  return (
    <Card
      title="채널별 성장률"
      style={{ marginBottom: 16 }}
      styles={{ body: { padding: 16 } }}
    >
      {growthData.length === 0 ? (
        <div
          style={{
            padding: 24,
            textAlign: "center",
            color: "rgba(0,0,0,0.45)",
          }}
        >
          데이터가 없습니다
        </div>
      ) : (
        <Row gutter={[16, 16]}>
          {growthData.map((card) => {
            const isPositive = card.growth_rate >= 0;
            const accent = isPositive ? "#52c41a" : "#cf1322";
            const platformLabel = PLATFORM_LABELS[card.platform] ?? card.platform;
            const languageLabel = LANGUAGE_LABELS[card.language] ?? card.language;
            // 채널 식별: 브랜드 · 플랫폼 · 언어 · 핸들. 백필 전(client=null)이면 브랜드를 생략한다.
            const channelName = `${card.client ? `${card.client} · ` : ""}${platformLabel} · ${languageLabel}${card.handle ? ` · ${card.handle}` : ""}`;
            return (
              <Col
                xs={24}
                sm={12}
                md={8}
                lg={6}
                key={`${card.client ?? ""}-${card.platform}-${card.language}-${card.handle ?? ""}`}
              >
                <Card
                  hoverable
                  style={{ borderLeft: `3px solid ${accent}` }}
                  styles={{ body: { padding: "16px 20px" } }}
                >
                  <div
                    style={{
                      fontSize: 13,
                      color: "rgba(0,0,0,0.55)",
                      marginBottom: 8,
                      fontWeight: 500,
                    }}
                  >
                    {channelName}
                  </div>
                  <Statistic
                    value={card.current_followers}
                    formatter={(val) => formatNumber(Number(val))}
                    valueStyle={{ fontSize: 22, fontWeight: 700 }}
                  />
                  <div
                    style={{
                      marginTop: 8,
                      color: accent,
                      fontWeight: 600,
                      fontSize: 13,
                      display: "flex",
                      alignItems: "center",
                      gap: 4,
                    }}
                  >
                    {isPositive ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
                    {formatPercent(card.growth_rate)}
                    <span
                      style={{
                        color: "rgba(0,0,0,0.45)",
                        fontWeight: 400,
                        marginLeft: 4,
                      }}
                    >
                      전 주 대비
                    </span>
                  </div>
                </Card>
              </Col>
            );
          })}
        </Row>
      )}
    </Card>
  );
}
