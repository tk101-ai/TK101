import type { PlaygroundTaskStatus } from "../../../api/playground";

export type MediaKind = "image" | "video";

export interface MediaGenPanelProps {
  kind: MediaKind;
}

export interface ActiveTask {
  // DB row 의 id (있으면 안정 URL 서빙 가능).
  mediaId: string | null;
  taskId: string;
  kind: MediaKind;
  prompt: string;
  modelKey: string;
  status: PlaygroundTaskStatus["status"];
  outputUrl: string | null;
  errorMessage: string | null;
  costUsd: number | null;
  // i2v 참고 이미지 row id(영상이 어떤 이미지로 만들어졌는지 표시용).
  sourceMediaId: string | null;
  // 생성 시각 (ISO). DB 복원 시 created_at, 신규 요청 시 클라이언트 now.
  createdAt: string;
}

export interface DateGroup {
  dateKey: string;
  label: string;
  tasks: ActiveTask[];
}

export interface I2VFormValues {
  prompt: string;
  model_key: string;
  duration: number;
  resolution: string;
  aspect_ratio: string;
  audio_generation: boolean;
  enhance_prompt: boolean;
}

/** i2i 리터치/편집 모달 입력값. */
export interface ImageEditFormValues {
  prompt: string;
  model_key: string;
  aspect_ratio: string;
  enhance_prompt: boolean;
}
