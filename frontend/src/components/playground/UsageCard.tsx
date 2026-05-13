import { Card, Typography } from "antd";
import type { CumulativeUsage } from "../../hooks/usePlaygroundChat";

const { Text } = Typography;

interface UsageCardProps {
  usage: CumulativeUsage;
}

interface Row {
  label: string;
  value: number;
}

function formatNumber(n: number): string {
  return n.toLocaleString("en-US");
}

/**
 * 좌측 하단 누적 사용량 카드 (텐센트 원본 "CUMULATIVE USAGE" 복제).
 *
 * Phase 1은 backend usage endpoint가 아직 없어서, 채팅 훅의 in-memory
 * 누적치를 보여준다. 페이지 리프레시 시 0으로 초기화.
 */
export default function UsageCard({ usage }: UsageCardProps) {
  const rows: Row[] = [
    { label: "Total Requests", value: usage.totalRequests },
    { label: "Total Input Tokens", value: usage.totalInput },
    { label: "Total Output Tokens", value: usage.totalOutput },
    { label: "Total Tokens", value: usage.totalTokens },
    { label: "Cached Tokens", value: usage.cached },
    { label: "Reasoning Tokens", value: usage.reasoning },
    { label: "Images Generated", value: usage.imagesGenerated },
    { label: "Video Seconds", value: usage.videoSeconds },
  ];

  return (
    <Card
      size="small"
      title={
        <Text style={{ fontSize: 11, letterSpacing: "0.05em", color: "rgba(0,0,0,0.55)" }}>
          CUMULATIVE USAGE
        </Text>
      }
      styles={{ body: { padding: "8px 12px" } }}
    >
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        {rows.map((r) => (
          <div
            key={r.label}
            style={{
              display: "flex",
              justifyContent: "space-between",
              fontSize: 12,
              lineHeight: "18px",
            }}
          >
            <span style={{ color: "rgba(0,0,0,0.65)" }}>{r.label}</span>
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{formatNumber(r.value)}</span>
          </div>
        ))}
      </div>
    </Card>
  );
}
