import api from "./client";

export type NasFileType = "document" | "image";

export type NasFileKind = "pdf" | "word" | "ppt" | "hwp" | "excel";

export interface NasSearchParams {
  query: string;
  limit: number;
  file_kinds?: NasFileKind[];
  path_prefix?: string;
  mtime_from?: string;
  mtime_to?: string;
}

export interface NasTopFoldersResponse {
  folders: string[];
}

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
  // Qdrant 엔진 전환 후: file_type 은 다양한 문자열, mime/size/mtime 은 없을 수 있음.
  file_type: string;
  mime_type: string | null;
  size: number | null;
  mtime: string | null;
  dept?: string | null;  // 부서(신사업/RND/마케팅 등) — 새 데이터 출처 표시
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

export const searchNasText = (params: NasSearchParams) =>
  api.post<NasSearchResponse>("/api/nas/search/text", params);

export const getNasTopFolders = () =>
  api.get<NasTopFoldersResponse>("/api/nas/folders/top");

/**
 * JWT Bearer 인증을 유지한 채 파일을 다운로드한다.
 * 새 탭/window.open은 Authorization 헤더를 못 붙이므로 axios blob으로 받아 처리.
 */
export async function downloadNasFile(path: string, filename: string): Promise<void> {
  // Qdrant 검색결과는 nas_files id가 없으므로 경로 기반 다운로드.
  const res = await api.get<Blob>(`/api/nas/files/download`, {
    params: { path },
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
