import api from "./client";

export type NasFileType = "document" | "image";

export interface NasStatus {
  mount_ok: boolean;
  mount_path: string;
  total_files: number;
  indexed_files: number;
  last_indexed_at: string | null;
}

export interface NasIndexStatus {
  running: boolean;
  processed: number;
  total: number;
  current_path: string | null;
  errors: number;
  started_at: string | null;
  finished_at: string | null;
  last_error: string | null;
}

export interface NasSearchHit {
  id: string;
  path: string;
  name: string;
  file_type: NasFileType;
  mime_type: string;
  size: number;
  mtime: string;
  score: number;
  snippet: string | null;
}

export interface NasSearchResponse {
  results: NasSearchHit[];
}

export interface NasIndexRunResponse {
  task_id: string;
  status: "queued" | "running";
}

export const getNasStatus = () => api.get<NasStatus>("/api/nas/status");

export const runNasIndex = () =>
  api.post<NasIndexRunResponse>("/api/nas/index/run");

export const getNasIndexStatus = () =>
  api.get<NasIndexStatus>("/api/nas/index/status");

export const searchNasText = (query: string, limit: number = 20) =>
  api.post<NasSearchResponse>("/api/nas/search/text", { query, limit });

/**
 * JWT Bearer 인증을 유지한 채 파일을 다운로드한다.
 * 새 탭/window.open은 Authorization 헤더를 못 붙이므로 axios blob으로 받아 처리.
 */
export async function downloadNasFile(id: string, filename: string): Promise<void> {
  const res = await api.get<Blob>(`/api/nas/files/${encodeURIComponent(id)}/download`, {
    responseType: "blob",
  });
  const url = window.URL.createObjectURL(res.data);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}
