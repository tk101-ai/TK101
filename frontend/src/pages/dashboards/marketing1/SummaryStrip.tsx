import { Card, Col, Row, Statistic } from "antd";
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import {
  PLATFORM_ICONS,
  PLATFORM_LABELS,
  formatNumber,
  formatPercent,
} from "./constants";
import type { PlatformSummary, TotalsSummary } from "./types";

interface SummaryStripProps {
  month: number;
  totals: TotalsSummary;
  platformSummaries: PlatformSummary[];
}

export default function SummaryStrip({
  month,
  totals,
  platformSummaries,
}: SummaryStripProps) {
  return (
    <>
      {/* 통합 요약 스트립: 전 플랫폼·전 계정 합산 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} sm={12} md={6}>
          <Card styles={{ body: { padding: "16px 20px" } }}>
            <Statistic
              title="총 팔로워"
              value={totals.totalFollowers}
              prefix={<TeamOutlined style={{ color: "#1677ff" }} />}
              formatter={(val) => formatNumber(Number(val))}
              valueStyle={{ fontSize: 24, fontWeight: 700 }}
            />
            <div
              style={{
                marginTop: 6,
                fontSize: 13,
                fontWeight: 600,
                color: totals.followerGrowthRate >= 0 ? "#52c41a" : "#cf1322",
              }}
            >
              {totals.followerGrowthRate >= 0 ? (
                <ArrowUpOutlined />
              ) : (
                <ArrowDownOutlined />
              )}{" "}
              {formatPercent(totals.followerGrowthRate * 100)}
              <span style={{ color: "rgba(0,0,0,0.45)", fontWeight: 400, marginLeft: 4 }}>
                전 주 대비
              </span>
            </div>
          </Card>
        </Col>
        <Col xs={12} sm={12} md={6}>
          <Card styles={{ body: { padding: "16px 20px" } }}>
            <Statistic
              title={`이번 달 게시물 (${month}월)`}
              value={totals.monthPostCount}
              formatter={(val) => formatNumber(Number(val))}
              valueStyle={{ fontSize: 24, fontWeight: 700 }}
              suffix="건"
            />
          </Card>
        </Col>
        <Col xs={12} sm={12} md={6}>
          <Card styles={{ body: { padding: "16px 20px" } }}>
            <Statistic
              title="총 조회수"
              value={totals.totalViews}
              formatter={(val) => formatNumber(Number(val))}
              valueStyle={{ fontSize: 24, fontWeight: 700 }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={12} md={6}>
          <Card styles={{ body: { padding: "16px 20px" } }}>
            <Statistic
              title="평균 참여율"
              value={totals.avgEngagementRate * 100}
              precision={2}
              suffix="%"
              valueStyle={{ fontSize: 24, fontWeight: 700 }}
            />
            <div style={{ marginTop: 6, fontSize: 12, color: "rgba(0,0,0,0.45)" }}>
              반응수 / 조회수
            </div>
          </Card>
        </Col>
      </Row>

      {/* 플랫폼별 카드 행: 계정 집합에서 동적 파생 */}
      {platformSummaries.length > 0 && (
        <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
          {platformSummaries.map((p) => {
            const positive = p.growthRate >= 0;
            const accent = positive ? "#52c41a" : "#cf1322";
            return (
              <Col xs={24} sm={12} md={8} key={p.platform}>
                <Card hoverable styles={{ body: { padding: "18px 20px" } }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                      marginBottom: 12,
                      fontSize: 16,
                      fontWeight: 600,
                    }}
                  >
                    <span style={{ fontSize: 22 }}>
                      {PLATFORM_ICONS[p.platform] ?? null}
                    </span>
                    {PLATFORM_LABELS[p.platform] ?? p.platform}
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
                    <div>
                      <div style={{ fontSize: 12, color: "rgba(0,0,0,0.45)" }}>
                        팔로워
                      </div>
                      <div style={{ fontSize: 22, fontWeight: 700 }}>
                        {formatNumber(p.followers)}
                      </div>
                      <div style={{ fontSize: 12, fontWeight: 600, color: accent, marginTop: 2 }}>
                        {positive ? <ArrowUpOutlined /> : <ArrowDownOutlined />}{" "}
                        {formatPercent(p.growthRate * 100)}
                      </div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <div style={{ fontSize: 12, color: "rgba(0,0,0,0.45)" }}>
                        게시물 / 조회수
                      </div>
                      <div style={{ fontSize: 15, fontWeight: 600 }}>
                        {formatNumber(p.postCount)}건
                      </div>
                      <div style={{ fontSize: 13, color: "rgba(0,0,0,0.65)" }}>
                        {formatNumber(p.viewCount)}
                      </div>
                    </div>
                  </div>
                </Card>
              </Col>
            );
          })}
        </Row>
      )}
    </>
  );
}
