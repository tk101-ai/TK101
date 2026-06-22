import api from "./client";

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
}

export interface DocGenRequest {
  topic: string;
  doc_type: DocType;
  /** 출처 모드. 기본 "rag"(NAS만). */
  source_mode?: SourceMode;
  limit?: number;
  /** source_mode 가 uploaded/both 일 때 참고할 업로드 파일들. */
  files?: File[];
}

export interface DocGenResponse {
  title: string;
  sections: DocSection[];
  markdown: string;
  sources: DocSourceRef[];
  cost_usd: number;
  model: string;
}

export async function generateDocument(req: DocGenRequest): Promise<DocGenResponse> {
  // 멀티파트 — 업로드 파일을 참고자료로 함께 전송한다.
  const fd = new FormData();
  fd.append("topic", req.topic);
  fd.append("doc_type", req.doc_type);
  fd.append("source_mode", req.source_mode ?? "rag");
  fd.append("limit", String(req.limit ?? 8));
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
  use_nas: boolean;
}

export interface RegenerateSectionResponse {
  section: DocSection;
  cost_usd: number;
  model: string;
}

/** 초안의 한 섹션만 (수정 요청 반영) 재생성. */
export async function regenerateSection(
  req: RegenerateSectionRequest,
): Promise<RegenerateSectionResponse> {
  const res = await api.post<RegenerateSectionResponse>("/api/docgen/regenerate_section", req);
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
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${title || "문서"}.docx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
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
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${title || "문서"}.pptx`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
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
  cost_usd: number;
  model: string;
}

/** 생성 초안 품질검증(LLM-as-judge). */
export async function reviewDocument(req: {
  topic: string;
  doc_type: DocType;
  title: string;
  sections: DocSection[];
  use_nas: boolean;
}): Promise<DocReviewResponse> {
  const res = await api.post<DocReviewResponse>("/api/docgen/review", req);
  return res.data;
}
