import api from "./client";
import { triggerBlobDownload } from "../utils/download";

export type DocType = "제안서" | "계획서" | "보고서" | "일반";

/** 출처 모드 — 회사 NAS RAG만 / 사용자 업로드만 / 둘다. */
export type SourceMode = "rag" | "uploaded" | "both";

export interface DocSection {
  heading: string;
  body: string;
}

export interface DocSourceRef {
  path: string;
  score: number;
  /** 표시용 파일명(있으면 path 대신 노출). */
  name?: string | null;
  /** 출처 구분: "nas"(회사 NAS RAG) / "uploaded"(사용자 업로드). */
  source_type: "nas" | "uploaded";
  /** NAS 문서 doc_id(업로드 자료는 빈 문자열/null). */
  doc_id?: string | null;
  /** LLM 이 실제 인용했다고 보고한 자료 여부. false 여도 생성 컨텍스트엔 주입됨. */
  cited?: boolean;
}

export interface DocGenRequest {
  topic: string;
  doc_type: DocType;
  /** 출처 모드. 기본 "rag"(NAS만). */
  source_mode?: SourceMode;
  limit?: number;
  /** 고품질 모드(LLM 검수→재생성 루프). 기본 false(초안, 빠름). */
  auto_review?: boolean;
  /** source_mode 가 uploaded/both 일 때 참고할 업로드 파일들. */
  files?: File[];
}

export interface DocGenResponse {
  title: string;
  sections: DocSection[];
  markdown: string;
  sources: DocSourceRef[];
  // cost_usd 는 관리자 전용 패널로 이전 — 일반 응답에서 제외.
  model: string;
  /** 영속화된 문서 id(재열람 키). 저장 실패 시 null. */
  document_id?: string | null;
}

/** 내 문서 목록 항목(가벼운 메타만). */
export interface DocgenDocumentBrief {
  id: string;
  title: string;
  doc_type?: string | null;
  created_at: string;
}

/** 재열람용 전체 문서(섹션/출처 포함). */
export interface DocgenDocumentDetail {
  id: string;
  title: string;
  sections: DocSection[];
  sources: DocSourceRef[];
  topic?: string | null;
  doc_type?: DocType | null;
  source_mode?: SourceMode | null;
  created_at: string;
}

/** 본인이 저장한 생성 문서 목록(최신순). q 가 있으면 제목/주제 ILIKE 검색. */
export async function listDocgenDocuments(
  q?: string,
): Promise<DocgenDocumentBrief[]> {
  const params: Record<string, string> = {};
  if (q && q.trim()) params.q = q.trim();
  const res = await api.get<DocgenDocumentBrief[]>("/api/docgen/documents", {
    params,
  });
  return res.data;
}

/** 저장된 문서 1건 전체(재열람용). */
export async function getDocgenDocument(
  id: string,
): Promise<DocgenDocumentDetail> {
  const res = await api.get<DocgenDocumentDetail>(
    `/api/docgen/documents/${id}`,
  );
  return res.data;
}

/** 본인 문서 삭제. */
export async function deleteDocgenDocument(id: string): Promise<void> {
  await api.delete(`/api/docgen/documents/${id}`);
}

export async function generateDocument(req: DocGenRequest): Promise<DocGenResponse> {
  // 멀티파트 — 업로드 파일을 참고자료로 함께 전송한다.
  const fd = new FormData();
  fd.append("topic", req.topic);
  fd.append("doc_type", req.doc_type);
  fd.append("source_mode", req.source_mode ?? "rag");
  fd.append("limit", String(req.limit ?? 8));
  // 고품질 모드 토글 — 명시한 경우에만 전송(미전송 시 서버 기본값 적용).
  if (req.auto_review !== undefined) {
    fd.append("auto_review", String(req.auto_review));
  }
  (req.files ?? []).forEach((f) => fd.append("files", f));
  const res = await api.post<DocGenResponse>("/api/docgen/generate", fd);
  return res.data;
}

export interface RegenerateSectionRequest {
  topic: string;
  doc_type: DocType;
  heading: string;
  current_body: string;
  feedback: string;
  /** 출처 모드. 기본 "rag"(NAS만). */
  source_mode?: SourceMode;
  /** source_mode 가 uploaded/both 일 때 참고할 업로드 파일들. */
  files?: File[];
}

export interface RegenerateSectionResponse {
  section: DocSection;
  model: string;
}

/** 초안의 한 섹션만 (수정 요청 반영) 재생성. */
export async function regenerateSection(
  req: RegenerateSectionRequest,
): Promise<RegenerateSectionResponse> {
  // 멀티파트 — 업로드 자료/출처모드를 재생성에도 함께 전송한다.
  const fd = new FormData();
  fd.append("topic", req.topic);
  fd.append("doc_type", req.doc_type);
  fd.append("heading", req.heading);
  fd.append("current_body", req.current_body);
  fd.append("feedback", req.feedback);
  fd.append("source_mode", req.source_mode ?? "rag");
  (req.files ?? []).forEach((f) => fd.append("files", f));
  const res = await api.post<RegenerateSectionResponse>(
    "/api/docgen/regenerate_section",
    fd,
  );
  return res.data;
}

/** 초안(수정 가능)을 .docx 로 렌더해 브라우저 다운로드. */
export async function downloadGeneratedDocx(
  title: string,
  sections: DocSection[],
): Promise<void> {
  const res = await api.post(
    "/api/docgen/render",
    { title, sections },
    { responseType: "blob" },
  );
  const blob = new Blob([res.data], {
    type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  });
  triggerBlobDownload(blob, `${title || "문서"}.docx`);
}

/** 초안(수정 가능)을 .pptx 로 렌더해 브라우저 다운로드. */
export async function downloadGeneratedPptx(
  title: string,
  sections: DocSection[],
): Promise<void> {
  const res = await api.post(
    "/api/docgen/render_pptx",
    { title, sections },
    { responseType: "blob" },
  );
  const blob = new Blob([res.data], {
    type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
  });
  triggerBlobDownload(blob, `${title || "문서"}.pptx`);
}

export interface DocSectionReview {
  heading: string;
  grounded: boolean;
  issues: string[];
  suggestions: string[];
}

export interface DocReviewResponse {
  overall_score: number;
  summary: string;
  section_reviews: DocSectionReview[];
  missing: string[];
  model: string;
}

/** 생성 초안 품질검증(LLM-as-judge). */
export async function reviewDocument(req: {
  topic: string;
  doc_type: DocType;
  title: string;
  sections: DocSection[];
  /** 출처 모드. 기본 "rag"(NAS만). */
  source_mode?: SourceMode;
  /** source_mode 가 uploaded/both 일 때 참고할 업로드 파일들. */
  files?: File[];
}): Promise<DocReviewResponse> {
  // 멀티파트 — sections 는 JSON 문자열로, 업로드 자료는 파일로 함께 전송한다.
  const fd = new FormData();
  fd.append("topic", req.topic);
  fd.append("doc_type", req.doc_type);
  fd.append("title", req.title);
  fd.append("sections_json", JSON.stringify(req.sections));
  fd.append("source_mode", req.source_mode ?? "rag");
  (req.files ?? []).forEach((f) => fd.append("files", f));
  const res = await api.post<DocReviewResponse>("/api/docgen/review", fd);
  return res.data;
}

// ---------------------------------------------------------------------------
// 리터치 프롬프트 (디자인/내용 프리셋)
// ---------------------------------------------------------------------------

/** 어떤 AI용으로 다듬을지. internal=우리 생성기 재생성용. */
export type RetouchTarget = "general" | "gamma" | "gpt" | "gemini" | "internal";

export interface RetouchPromptResult {
  prompt_text: string;
  target: RetouchTarget;
  model: string;
}

export interface RetouchPreset {
  id: string;
  title: string;
  doc_type?: string | null;
  target: RetouchTarget;
  prompt_text: string;
  is_shared: boolean;
  shared_at: string | null;
  source_document_id?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface SharedRetouchPreset extends RetouchPreset {
  owner_name: string | null;
  owner_department: string | null;
  is_mine: boolean;
}

/** 현재 초안(편집 가능)으로 리터치 프롬프트 생성. */
export async function generateRetouchPrompt(req: {
  title: string;
  sections: DocSection[];
  doc_type: DocType;
  topic?: string | null;
  target: RetouchTarget;
  source_document_id?: string | null;
}): Promise<RetouchPromptResult> {
  const res = await api.post<RetouchPromptResult>("/api/docgen/retouch-prompt", req);
  return res.data;
}

/** 리터치 프롬프트를 프리셋으로 저장. */
export async function saveRetouchPreset(body: {
  title: string;
  prompt_text: string;
  doc_type?: DocType | null;
  target: RetouchTarget;
  source_document_id?: string | null;
}): Promise<RetouchPreset> {
  const res = await api.post<RetouchPreset>("/api/docgen/retouch-prompts", body);
  return res.data;
}

/** 내 프리셋 목록(최신순). */
export async function listRetouchPresets(
  q?: string,
  docType?: string,
): Promise<RetouchPreset[]> {
  const params: Record<string, string> = {};
  if (q && q.trim()) params.q = q.trim();
  if (docType) params.doc_type = docType;
  const res = await api.get<RetouchPreset[]>("/api/docgen/retouch-prompts", {
    params,
  });
  return res.data;
}

/** 공유 프리셋 목록(전체, 최신 공유순). */
export async function listSharedRetouchPresets(
  q?: string,
  docType?: string,
): Promise<SharedRetouchPreset[]> {
  const params: Record<string, string> = {};
  if (q && q.trim()) params.q = q.trim();
  if (docType) params.doc_type = docType;
  const res = await api.get<SharedRetouchPreset[]>(
    "/api/docgen/retouch-prompts/shared",
    { params },
  );
  return res.data;
}

/** 프리셋 수정 — 제목/본문 편집 또는 공유 토글. */
export async function updateRetouchPreset(
  id: string,
  patch: { title?: string; prompt_text?: string; is_shared?: boolean },
): Promise<RetouchPreset> {
  const res = await api.patch<RetouchPreset>(
    `/api/docgen/retouch-prompts/${id}`,
    patch,
  );
  return res.data;
}

/** 프리셋 삭제. */
export async function deleteRetouchPreset(id: string): Promise<void> {
  await api.delete(`/api/docgen/retouch-prompts/${id}`);
}
