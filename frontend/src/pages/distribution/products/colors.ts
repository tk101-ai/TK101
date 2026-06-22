// ---------------------------------------------------------------------------
// 색상 매핑 — 라벨을 해시해 색을 결정. 브랜드/카테고리가 나중에 추가돼도
// 자동으로 일관된 색이 부여된다(하드코딩 매핑 제거: 동적 설계 원칙).
// ---------------------------------------------------------------------------

// antd preset 태그 색상 팔레트(default 제외) — 해시 결과를 이 중 하나로 매핑.
const TAG_COLORS = [
  "magenta",
  "red",
  "volcano",
  "orange",
  "gold",
  "lime",
  "green",
  "cyan",
  "blue",
  "geekblue",
  "purple",
] as const;

// 라벨 → 안정적 색상. 동일 라벨은 항상 같은 색(대소문자 무시).
function colorForLabel(label: string): string {
  const key = label.trim().toLowerCase();
  let hash = 0;
  for (let i = 0; i < key.length; i += 1) {
    hash = (hash * 31 + key.charCodeAt(i)) | 0;
  }
  const idx = Math.abs(hash) % TAG_COLORS.length;
  return TAG_COLORS[idx];
}

export function getCategoryColor(cat: string | null): string {
  if (!cat) return "default";
  return colorForLabel(cat);
}

export function getBrandColor(brand: string): string {
  if (!brand) return "default";
  return colorForLabel(brand);
}
