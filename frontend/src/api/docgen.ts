import api from "./client";

export type DocType = "제안서" | "계획서" | "보고서" | "일반";

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
  use_nas: boolean;
  limit?: number;
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
  const res = await api.post<DocGenResponse>("/api/docgen/generate", {
    topic: req.topic,
    doc_type: req.doc_type,
    use_nas: req.use_nas,
    limit: req.limit ?? 8,
  });
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
