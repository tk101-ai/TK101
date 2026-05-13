import { Tag } from "antd";
import type { PlaygroundModelVariant } from "../../api/playground";

interface ModelChipListProps {
  variants: PlaygroundModelVariant[];
  selectedId: string;
  onSelect: (id: string) => void;
}

/**
 * 선택된 공급자의 변형(chip) 리스트.
 * Antd `Tag` 의 `Tag.CheckableTag` 형식으로 토글된다.
 */
export default function ModelChipList({ variants, selectedId, onSelect }: ModelChipListProps) {
  if (variants.length === 0) {
    return (
      <div style={{ fontSize: 11, color: "rgba(0,0,0,0.45)" }}>변형이 없습니다</div>
    );
  }
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
      {variants.map((v) => {
        const selected = v.id === selectedId;
        return (
          <Tag.CheckableTag
            key={v.id}
            checked={selected}
            onChange={() => onSelect(v.id)}
            style={{
              fontSize: 12,
              padding: "2px 10px",
              borderRadius: 12,
              border: selected ? "1px solid #722ed1" : "1px solid rgba(0,0,0,0.12)",
            }}
          >
            {v.label}
            {v.badge ? (
              <span
                style={{
                  marginLeft: 6,
                  fontSize: 10,
                  padding: "0 4px",
                  borderRadius: 4,
                  background: "#722ed1",
                  color: "#fff",
                }}
              >
                {v.badge}
              </span>
            ) : null}
          </Tag.CheckableTag>
        );
      })}
    </div>
  );
}
