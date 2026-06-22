/**
 * 세션 상세 화면 전용 포맷터 / 상수.
 *
 * SessionDetailPage 에서 추출(순수 리팩토링). 출력 형식은 기존과 동일.
 */
import dayjs from "dayjs";

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return dayjs(iso).format("YYYY-MM-DD HH:mm:ss");
}

export function formatCost(value: string | null): string {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  return `$${n.toFixed(4)}`;
}

export function formatCumulativeOffset(sec: number): string {
  if (sec < 60) return `+${sec}s`;
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (s === 0) return `+${m}m`;
  return `+${m}m ${s}s`;
}

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

/** send_after_sec 빠른 설정 프리셋. 라벨 = 사용자가 보는 텍스트, value = 초. */
export const TIMING_PRESETS: { label: string; value: number }[] = [
  { label: "즉시", value: 0 },
  { label: "1분", value: 60 },
  { label: "5분", value: 300 },
  { label: "30분", value: 1800 },
  { label: "1시간", value: 3600 },
  { label: "3시간", value: 10800 },
  { label: "6시간", value: 21600 },
  { label: "12시간", value: 43200 },
];

export const ATTACHMENT_ACCEPT =
  ".jpg,.jpeg,.png,.webp,.gif,.pdf,.xlsx,.xls,.csv,.hwp,.hwpx,.docx,.doc,.pptx,.ppt,.txt";
