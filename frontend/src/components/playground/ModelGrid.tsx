import { Card, Tag, Tooltip, Typography } from "antd";
import type { PlaygroundProvider, PlaygroundProviderKey } from "../../api/playground";

const { Text } = Typography;

interface ModelGridProps {
  providers: PlaygroundProvider[];
  selectedKey: PlaygroundProviderKey;
  onSelect: (key: PlaygroundProviderKey) => void;
}

/**
 * 좌측 사이드바: 모델 공급자 카드 3×3 그리드.
 *
 * - 활성 카드만 클릭 가능, 비활성은 disabled 톤 + "준비 중" 툴팁
 * - 선택된 카드는 하이라이트 (보라 borderColor)
 * - 우상단 버전 뱃지 ("3v" 등)
 */
export default function ModelGrid({ providers, selectedKey, onSelect }: ModelGridProps) {
  // 3×3 자리 보장: 부족하면 빈 placeholder 카드를 채워둔다.
  const cells: (PlaygroundProvider | null)[] = [...providers];
  while (cells.length < 9) cells.push(null);
  const trimmed = cells.slice(0, 9);

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(3, 1fr)",
        gap: 6,
      }}
    >
      {trimmed.map((p, idx) => {
        if (!p) {
          return (
            <div
              key={`empty-${idx}`}
              style={{
                aspectRatio: "1 / 1",
                border: "1px dashed rgba(0,0,0,0.12)",
                borderRadius: 8,
                background: "transparent",
              }}
            />
          );
        }
        const selected = p.enabled && p.key === selectedKey;
        const card = (
          <Card
            size="small"
            hoverable={p.enabled}
            onClick={() => p.enabled && onSelect(p.key)}
            style={{
              cursor: p.enabled ? "pointer" : "not-allowed",
              opacity: p.enabled ? 1 : 0.45,
              borderColor: selected ? "#722ed1" : undefined,
              borderWidth: selected ? 2 : 1,
              position: "relative",
              aspectRatio: "1 / 1",
            }}
            styles={{ body: { padding: 8, height: "100%" } }}
          >
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                height: "100%",
              }}
            >
              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <Tag
                  color={selected ? "purple" : "default"}
                  style={{ marginInlineEnd: 0, fontSize: 10, padding: "0 4px", lineHeight: "16px" }}
                >
                  {p.versionBadge}
                </Tag>
              </div>
              <div style={{ textAlign: "center" }}>
                <Text strong style={{ fontSize: 12 }}>
                  {p.name}
                </Text>
              </div>
            </div>
          </Card>
        );
        if (!p.enabled) {
          return (
            <Tooltip key={p.key} title="후속 Phase에서 활성화됩니다">
              {card}
            </Tooltip>
          );
        }
        return <div key={p.key}>{card}</div>;
      })}
    </div>
  );
}
