// ---------------------------------------------------------------------------
// Transactions 페이지 전용 포맷터
// ---------------------------------------------------------------------------

export function formatAmount(v: string | null | undefined): string {
  if (v == null || v === "") return "-";
  return `${Number(v).toLocaleString("ko-KR")}원`;
}
