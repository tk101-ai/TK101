import { useCallback, useEffect, useState } from "react";
import { Progress, Spin, Tooltip, Typography } from "antd";
import { WalletOutlined } from "@ant-design/icons";
import { getMyQuota, type PlaygroundQuotaInfo } from "../../api/playground";

const { Text } = Typography;

interface QuotaIndicatorProps {
  /**
   * 부모가 변경할 때마다 (예: 메시지 전송 직후) 재조회 트리거.
   * 변경되면 fetch 한 번 더 실행.
   */
  refreshKey?: number;
}

function num(v: number | string | null | undefined): number {
  if (v === null || v === undefined) return 0;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : 0;
}

/**
 * 본인 이번 달 한도 / 사용량 / 남은 금액을 한 줄로 표시.
 *
 * - 컴포넌트 mount 시 1회 + refreshKey 변경 시 fetch.
 * - 권한 / 네트워크 실패는 무음 (조용히 숨김).
 */
export default function QuotaIndicator({ refreshKey = 0 }: QuotaIndicatorProps) {
  const [quota, setQuota] = useState<PlaygroundQuotaInfo | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchQuota = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getMyQuota();
      setQuota(data);
    } catch {
      setQuota(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchQuota();
  }, [fetchQuota, refreshKey]);

  if (loading && !quota) {
    return (
      <div style={{ padding: "6px 10px", textAlign: "center" }}>
        <Spin size="small" />
      </div>
    );
  }

  if (!quota) {
    // 조용히 숨김 (한도 기능 비활성화된 환경 호환).
    return null;
  }

  const total = num(quota.monthly_quota_usd);
  const used = num(quota.current_usage_usd);
  const remaining = num(quota.remaining_usd);
  const pct = total > 0 ? Math.min(100, Math.round((used / total) * 100)) : 0;
  const status =
    pct >= 100 ? "exception" : pct >= 80 ? "active" : ("normal" as const);
  const strokeColor =
    pct >= 100 ? "#ff4d4f" : pct >= 80 ? "#faad14" : "#1677ff";

  return (
    <Tooltip
      title={
        <div style={{ fontSize: 12 }}>
          <div>이번 달 한도: ${total.toFixed(2)}</div>
          <div>사용: ${used.toFixed(4)}</div>
          <div>남음: ${remaining.toFixed(4)}</div>
          <div style={{ marginTop: 4, color: "rgba(255,255,255,0.65)" }}>
            기간: {quota.period_start?.slice(0, 10)} ~ {quota.period_end?.slice(0, 10)}
          </div>
        </div>
      }
    >
      <div
        style={{
          padding: "8px 10px",
          borderRadius: 8,
          border: "1px solid rgba(0,0,0,0.08)",
          background: "rgba(0,0,0,0.02)",
          display: "flex",
          flexDirection: "column",
          gap: 4,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <WalletOutlined style={{ fontSize: 13, color: strokeColor }} />
          <Text style={{ fontSize: 11, fontWeight: 600 }}>이번 달 사용량</Text>
        </div>
        <div style={{ fontSize: 12, lineHeight: 1.4 }}>
          <Text strong>${used.toFixed(4)}</Text>
          <Text type="secondary"> / ${total.toFixed(2)}</Text>
        </div>
        <Progress
          percent={pct}
          showInfo={false}
          size="small"
          status={status}
          strokeColor={strokeColor}
        />
        <Text type="secondary" style={{ fontSize: 11 }}>
          남은 ${remaining.toFixed(4)}
        </Text>
      </div>
    </Tooltip>
  );
}
