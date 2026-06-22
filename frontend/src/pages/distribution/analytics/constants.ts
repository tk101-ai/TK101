export const SESSION_STATUS_KEYS = [
  "pending",
  "approved",
  "rejected",
  "sending",
  "sent",
  "failed",
] as const;

export const SESSION_STATUS_LABEL: Record<string, string> = {
  pending: "검수 대기",
  approved: "승인됨",
  rejected: "거부됨",
  sending: "송신 중",
  sent: "송신 완료",
  failed: "실패",
};

export const SESSION_STATUS_COLOR: Record<string, string> = {
  pending: "#faad14",
  approved: "#52c41a",
  rejected: "#bfbfbf",
  sending: "#1677ff",
  sent: "#3f8600",
  failed: "#cf1322",
};

export const MESSAGE_STATUS_COLOR: Record<string, string> = {
  queued: "default",
  sent: "green",
  failed: "red",
  skipped: "gold",
};

export const DEFAULT_RANGE_DAYS = 30;
