import { message } from "antd";
import { mediaFileUrl } from "../../../api/playground";
import type { PlaygroundMediaItem } from "../../../api/playground";
import { triggerBlobDownload } from "../../../utils/download";
import type { ActiveTask, DateGroup } from "./types";

export function itemToTask(item: PlaygroundMediaItem): ActiveTask {
  return {
    mediaId: item.id,
    taskId: item.task_id ?? item.id,
    kind: item.media_type,
    prompt: item.prompt ?? "",
    modelKey: item.model_key ?? "",
    status: item.status,
    outputUrl: item.file_path ? mediaFileUrl(item.id) : item.url,
    errorMessage: item.error_message,
    costUsd: item.cost_usd,
    sourceMediaId: item.source_media_id ?? null,
    sourceMediaKind: item.source_media_type ?? null,
    createdAt: item.created_at,
  };
}

/** 로컬 타임존 기준 YYYY-MM-DD 문자열. */
function toDateKey(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** dateKey(YYYY-MM-DD) → "오늘 / 어제 / YYYY-MM-DD" 헤더 라벨. */
function dateGroupLabel(dateKey: string): string {
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (dateKey === toDateKey(today)) return "오늘";
  if (dateKey === toDateKey(yesterday)) return "어제";
  return dateKey;
}

/**
 * task 목록을 생성 날짜(로컬 타임존)별로 그룹핑. 최신 날짜가 먼저, 각 그룹 내에서도
 * 입력 순서(최신순)를 유지한다. createdAt 파싱 실패 항목은 "오늘" 그룹에 둔다.
 */
export function groupTasksByDate(tasks: ActiveTask[]): DateGroup[] {
  const todayKey = toDateKey(new Date());
  const order: string[] = [];
  const buckets = new Map<string, ActiveTask[]>();
  for (const t of tasks) {
    const parsed = t.createdAt ? new Date(t.createdAt) : null;
    const key =
      parsed && !Number.isNaN(parsed.getTime()) ? toDateKey(parsed) : todayKey;
    if (!buckets.has(key)) {
      buckets.set(key, []);
      order.push(key);
    }
    buckets.get(key)!.push(t);
  }
  // 최신 날짜 우선 정렬.
  order.sort((a, b) => (a < b ? 1 : a > b ? -1 : 0));
  return order.map((dateKey) => ({
    dateKey,
    label: dateGroupLabel(dateKey),
    tasks: buckets.get(dateKey)!,
  }));
}

/**
 * 결과물(이미지/영상)을 사용자 PC 로 즉시 다운로드.
 *
 * - mediaId 가 있으면 백엔드 안정 URL(`/api/playground/media/{id}/file`) 사용 — same-origin
 *   이라 fetch + Blob 다 통과. 백엔드 디스크에 영구 보관된 파일이라 만료 위험도 없음.
 * - mediaId 없으면 텐센트 임시 URL 로 fallback. cross-origin 차단 시 새 탭으로.
 */
export async function downloadTaskOutput(task: ActiveTask): Promise<void> {
  const ext = task.kind === "image" ? "png" : "mp4";
  const safeModel = (task.modelKey || "media").replace(/[^a-zA-Z0-9_.-]/g, "_");
  const filename = `${safeModel}_${task.taskId.slice(0, 12)}.${ext}`;

  // 1) 안정 URL — 백엔드 stream 통해 다운로드.
  if (task.mediaId) {
    try {
      const res = await fetch(`/api/playground/media/${task.mediaId}/file`, {
        credentials: "include",
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      triggerBlobDownload(blob, filename);
      return;
    } catch (err) {
      // fall through 텐센트 URL 시도.
      console.warn("백엔드 미디어 fetch 실패, 텐센트 URL 로 fallback", err);
    }
  }

  // 2) 텐센트 임시 URL fallback — cross-origin CORS 허용되면 fetch+blob, 아니면 새 탭.
  if (!task.outputUrl) {
    message.error("다운로드 URL 이 없습니다");
    return;
  }
  try {
    const res = await fetch(task.outputUrl);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const blob = await res.blob();
    triggerBlobDownload(blob, filename);
  } catch {
    // CORS 거부 시 — 그냥 새 탭 열어서 사용자가 브라우저 다운로드 사용.
    window.open(task.outputUrl, "_blank", "noopener,noreferrer");
  }
}
