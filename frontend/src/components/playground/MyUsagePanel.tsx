import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Card, Progress, Spin, Statistic, Typography } from "antd";
import { ReloadOutlined, WalletOutlined } from "@ant-design/icons";
import { getMyQuota, type PlaygroundQuotaInfo } from "../../api/playground";

const { Title, Text, Paragraph } = Typography;

function num(v: number | string | null | undefined): number {
  if (v === null || v === undefined) return 0;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

/**
 * 일반 playground 사용자가 본인 월 한도 / 사용량 / 잔여를 직접 확인하는 패널.
 *
 * - admin 전용 모델별/사용자별 breakdown(UsagePage)과 별개로, 메인 PlaygroundPage
 *   "내 사용량" 탭에서 누구나 볼 수 있도록 한 가벼운 요약 뷰.
 * - 데이터 출처는 일반 사용자 접근 가능한 GET /api/playground/me/quota.
 */
export default function MyUsagePanel() {
  const [quota, setQuota] = useState<PlaygroundQuotaInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);

  const fetchQuota = useCallback(async () => {
    setLoading(true);
    setFailed(false);
    try {
      const data = await getMyQuota();
      setQuota(data);
    } catch {
      setQuota(null);
      setFailed(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchQuota();
  }, [fetchQuota]);

  if (loading && !quota) {
    return (
      <div style={{ padding: 48, textAlign: "center" }}>
        <Spin />
      </div>
    );
  }

  if (failed || !quota) {
    return (
      <Alert
        type="info"
        showIcon
        message="사용량 정보를 불러올 수 없습니다"
        description="한도 기능이 비활성화되었거나 일시적인 오류일 수 있습니다."
        action={
          <Button size="small" icon={<ReloadOutlined />} onClick={() => void fetchQuota()}>
            다시 시도
          </Button>
        }
      />
    );
  }

  const total = num(quota.monthly_quota_usd);
  const used = num(quota.current_usage_usd);
  const remaining = num(quota.remaining_usd);
  const pct = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;
  const status = pct >= 100 ? "exception" : pct >= 80 ? "active" : ("normal" as const);
  const strokeColor = pct >= 100 ? "#ff4d4f" : pct >= 80 ? "#faad14" : "#1677ff";

  return (
    <div style={{ maxWidth: 720 }}>
      <Card
        styles={{ body: { padding: 24 } }}
        style={{ borderRadius: 12 }}
        title={
          <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <WalletOutlined style={{ color: strokeColor }} />
            <Title level={5} style={{ margin: 0 }}>
              이번 달 내 사용량
            </Title>
          </span>
        }
        extra={
          <Button size="small" icon={<ReloadOutlined />} onClick={() => void fetchQuota()}>
            새로고침
          </Button>
        }
      >
        <Paragraph type="secondary" style={{ fontSize: 12, marginTop: -4 }}>
          기간: {quota.period_start?.slice(0, 10)} ~ {quota.period_end?.slice(0, 10)} (UTC 월 기준)
        </Paragraph>

        <div
          style={{
            display: "flex",
            gap: 32,
            flexWrap: "wrap",
            margin: "12px 0 20px",
          }}
        >
          <Statistic title="이번 달 한도" value={total} precision={2} prefix="$" />
          <Statistic
            title="사용 금액"
            value={used}
            precision={4}
            prefix="$"
            valueStyle={{ color: strokeColor }}
          />
          <Statistic title="잔여 금액" value={Math.max(0, remaining)} precision={4} prefix="$" />
        </div>

        <Progress percent={pct} status={status} strokeColor={strokeColor} />

        {pct >= 100 ? (
          <Alert
            type="error"
            showIcon
            style={{ marginTop: 16 }}
            message="이번 달 한도를 모두 사용했습니다"
            description="추가 사용이 필요하면 관리자에게 한도 상향을 요청하세요."
          />
        ) : pct >= 80 ? (
          <Alert
            type="warning"
            showIcon
            style={{ marginTop: 16 }}
            message="한도의 80% 이상을 사용했습니다"
          />
        ) : (
          <Text type="secondary" style={{ display: "block", marginTop: 16, fontSize: 12 }}>
            텍스트·이미지·영상 생성 비용이 합산되어 집계됩니다.
          </Text>
        )}
      </Card>
    </div>
  );
}
