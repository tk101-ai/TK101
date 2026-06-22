import type { PlaygroundTaskStatus } from "../../../api/playground";

export const POLL_INTERVAL_MS = 3000;
export const POLL_MAX_MS = 5 * 60 * 1000;

export const STATUS_COLOR: Record<PlaygroundTaskStatus["status"], string> = {
  pending: "default",
  running: "processing",
  succeeded: "success",
  failed: "error",
  unknown: "warning",
};

export const STATUS_LABEL: Record<PlaygroundTaskStatus["status"], string> = {
  pending: "대기 중",
  running: "생성 중",
  succeeded: "완료",
  failed: "실패",
  unknown: "알 수 없음",
};

export const ASPECT_RATIO_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "1:1", label: "1:1 (정사각)" },
  { value: "16:9", label: "16:9 (와이드)" },
  { value: "9:16", label: "9:16 (세로)" },
  { value: "4:3", label: "4:3" },
  { value: "3:4", label: "3:4" },
];

export const VIDEO_RESOLUTION_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "720P", label: "720P" },
  { value: "1080P", label: "1080P" },
];
