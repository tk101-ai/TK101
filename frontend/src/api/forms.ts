import api from "./client";

/**
 * T5 범용 문서 자동 작성기 API 클라이언트 (PRD 7.3 — 14개 엔드포인트).
 *
 * 백엔드(T5-B) 머지 전이라도 프론트가 5단계 클릭 통과 가능하도록,
 * `VITE_FORMS_MOCK=1` 일 때 mock 응답을 반환한다.
 */

export type FormVariableType =
  | "text"
  | "number"
  | "date"
  | "enum"
  | "checkbox"
  | "table_row"
  | "image";

export interface FormVariable {
  key: string;
  label: string;
  type: FormVariableType;
  location?: string;
  required?: boolean;
  default?: string | null;
  confidence?: number;
}

export type FormFileFormat = "docx" | "xlsx" | "hwpx" | "pdf_form";

export interface FormTemplate {
  id: string;
  name: string;
  version: number;
  file_hash: string;
  file_path: string;
  file_format: FormFileFormat;
  variables: FormVariable[];
  department_tags: string[];
  owner_dept: string | null;
  usage_count: number;
  is_active: boolean;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

export interface FormTemplateAnalyzeResponse {
  template_id: string;
  file_hash: string;
  name: string;
  version: number;
  variables: FormVariable[];
  cache_hit: boolean;
  cost_usd?: number;
}

export interface FormTemplateListItem {
  id: string;
  name: string;
  version: number;
  file_hash?: string;
  file_format?: FormFileFormat;
  department_tags: string[];
  usage_count: number;
  created_at?: string;
  updated_at?: string;
}

export type FormJobStatus =
  | "analyzing"
  | "collecting"
  | "mapping"
  | "reviewing"
  | "completed"
  | "failed";

export interface FormJob {
  id: string;
  template_id: string | null;
  user_id: string;
  department: string | null;
  status: FormJobStatus;
  output_path: string | null;
  cost_usd: number;
  total_tokens_in: number;
  total_tokens_out: number;
  langfuse_trace_id: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export type FormSourceKind = "nas_file" | "user_upload" | "user_input" | "web_search";

export interface FormDataSource {
  id: string;
  job_id: string;
  kind: FormSourceKind;
  nas_file_id: string | null;
  upload_path: string | null;
  nas_chunk_ids: string[] | null;
  extracted_text: string | null;
  display_name?: string;
  created_at: string;
}

export interface FormMapping {
  id: string;
  job_id: string;
  variable_key: string;
  value: string | null;
  source_id: string | null;
  source_excerpt: string | null;
  llm_confidence: number | null;
  reasoning: string | null;
  manual_override: boolean;
  confirmed: boolean;
  created_at: string;
  updated_at: string;
}

export interface FormJobDetail {
  job: FormJob;
  template: FormTemplate;
  sources: FormDataSource[];
  mappings: FormMapping[];
}

export interface FormRevision {
  id: string;
  job_id: string;
  variable_key: string;
  previous_value: string | null;
  new_value: string | null;
  change_type: "manual_edit" | "regenerate" | "user_filled" | "lock" | "unlock";
  feedback_comment: string | null;
  changed_by: string | null;
  changed_at: string;
}

// ----------------------------------------------------------------------------
// Mock 모드: 백엔드 머지 전 프론트 단독 5단계 클릭 통과를 위함.
// ----------------------------------------------------------------------------

const MOCK_ENABLED = import.meta.env.VITE_FORMS_MOCK === "1";

interface MockStore {
  templates: Map<string, FormTemplate>;
  jobs: Map<string, FormJob>;
  sources: Map<string, FormDataSource[]>;
  mappings: Map<string, FormMapping[]>;
}

const mockStore: MockStore = {
  templates: new Map(),
  jobs: new Map(),
  sources: new Map(),
  mappings: new Map(),
};

function mockId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

function nowIso(): string {
  return new Date().toISOString();
}

function buildMockTemplate(name: string, fileFormat: FormFileFormat): FormTemplate {
  const id = mockId("tpl");
  const variables: FormVariable[] = [
    { key: "report_date", label: "보고일자", type: "date", location: "p.1", required: true, confidence: 0.95 },
    { key: "campaign_name", label: "캠페인명", type: "text", location: "p.1", required: true, confidence: 0.92 },
    { key: "owner", label: "담당자", type: "text", location: "p.1", required: true, confidence: 0.88 },
    { key: "kpi_reach", label: "도달수", type: "number", location: "table.1.r2", required: false, confidence: 0.74 },
    { key: "kpi_engagement", label: "참여율", type: "number", location: "table.1.r3", required: false, confidence: 0.62 },
    { key: "summary", label: "요약 코멘트", type: "text", location: "p.3", required: true, confidence: 0.55 },
  ];
  return {
    id,
    name,
    version: 1,
    file_hash: `mockhash_${id}`,
    file_path: `/mock/forms/${name}`,
    file_format: fileFormat,
    variables,
    department_tags: [],
    owner_dept: null,
    usage_count: 0,
    is_active: true,
    created_by: null,
    created_at: nowIso(),
    updated_at: nowIso(),
  };
}

function buildMockMappings(template: FormTemplate, jobId: string, sources: FormDataSource[]): FormMapping[] {
  const primarySource = sources[0];
  return template.variables.map((v, idx) => {
    const hasSource = primarySource && idx % 4 !== 3; // 마지막은 누락
    const conf = hasSource ? Math.max(0.45, 0.95 - idx * 0.07) : null;
    return {
      id: mockId("map"),
      job_id: jobId,
      variable_key: v.key,
      value: hasSource ? `샘플 값 (${v.label})` : null,
      source_id: hasSource ? primarySource.id : null,
      source_excerpt: hasSource ? `발췌문 #${idx + 1}: ${v.label} 관련 내용 ...` : null,
      llm_confidence: conf,
      reasoning: hasSource ? `자료에서 ${v.label}에 해당하는 토큰 발견` : null,
      manual_override: false,
      confirmed: false,
      created_at: nowIso(),
      updated_at: nowIso(),
    };
  });
}

// ----------------------------------------------------------------------------
// 14개 엔드포인트 (PRD 7.3)
// ----------------------------------------------------------------------------

export async function analyzeFormTemplate(
  file: File,
): Promise<FormTemplateAnalyzeResponse> {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 500));
    const fmt: FormFileFormat = file.name.endsWith(".xlsx")
      ? "xlsx"
      : file.name.endsWith(".hwpx")
        ? "hwpx"
        : "docx";
    const tpl = buildMockTemplate(file.name.replace(/\.[^.]+$/, ""), fmt);
    mockStore.templates.set(tpl.id, tpl);
    return {
      template_id: tpl.id,
      file_hash: tpl.file_hash,
      name: tpl.name,
      version: tpl.version,
      variables: tpl.variables,
      cache_hit: false,
      cost_usd: 0,
    };
  }
  const fd = new FormData();
  fd.append("file", file);
  const res = await api.post<FormTemplateAnalyzeResponse>(
    "/api/forms/templates/analyze",
    fd,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return res.data;
}

export async function listFormTemplates(params?: {
  q?: string;
  dept?: string;
}): Promise<FormTemplateListItem[]> {
  if (MOCK_ENABLED) {
    return Array.from(mockStore.templates.values()).map((t) => ({
      id: t.id,
      name: t.name,
      version: t.version,
      file_format: t.file_format,
      department_tags: t.department_tags,
      usage_count: t.usage_count,
      updated_at: t.updated_at,
    }));
  }
  const res = await api.get<FormTemplateListItem[]>("/api/forms/templates", {
    params,
  });
  return res.data;
}

export async function getFormTemplate(id: string): Promise<FormTemplate> {
  if (MOCK_ENABLED) {
    const tpl = mockStore.templates.get(id);
    if (!tpl) throw new Error("template not found (mock)");
    return tpl;
  }
  const res = await api.get<FormTemplate>(`/api/forms/templates/${id}`);
  return res.data;
}

export async function patchFormTemplate(
  id: string,
  body: { name?: string; department_tags?: string[]; variables?: FormVariable[] },
): Promise<FormTemplate> {
  if (MOCK_ENABLED) {
    const tpl = mockStore.templates.get(id);
    if (!tpl) throw new Error("template not found (mock)");
    const next: FormTemplate = {
      ...tpl,
      ...body,
      variables: body.variables ?? tpl.variables,
      updated_at: nowIso(),
    };
    mockStore.templates.set(id, next);
    return next;
  }
  const res = await api.patch<FormTemplate>(`/api/forms/templates/${id}`, body);
  return res.data;
}

export async function deleteFormTemplate(id: string): Promise<void> {
  if (MOCK_ENABLED) {
    mockStore.templates.delete(id);
    return;
  }
  await api.delete(`/api/forms/templates/${id}`);
}

export async function createFormJob(templateId: string): Promise<FormJob> {
  if (MOCK_ENABLED) {
    const tpl = mockStore.templates.get(templateId);
    if (!tpl) throw new Error("template not found (mock)");
    const job: FormJob = {
      id: mockId("job"),
      template_id: templateId,
      user_id: "mock-user",
      department: null,
      status: "collecting",
      output_path: null,
      cost_usd: 0,
      total_tokens_in: 0,
      total_tokens_out: 0,
      langfuse_trace_id: null,
      error_message: null,
      created_at: nowIso(),
      completed_at: null,
    };
    mockStore.jobs.set(job.id, job);
    mockStore.sources.set(job.id, []);
    mockStore.mappings.set(job.id, []);
    return job;
  }
  const res = await api.post<FormJob>("/api/forms/jobs", { template_id: templateId });
  return res.data;
}

export async function getFormJob(id: string): Promise<FormJobDetail> {
  if (MOCK_ENABLED) {
    const job = mockStore.jobs.get(id);
    if (!job) throw new Error("job not found (mock)");
    const tpl = job.template_id ? mockStore.templates.get(job.template_id) : undefined;
    if (!tpl) throw new Error("template not found (mock)");
    return {
      job,
      template: tpl,
      sources: mockStore.sources.get(id) ?? [],
      mappings: mockStore.mappings.get(id) ?? [],
    };
  }
  const res = await api.get<FormJobDetail>(`/api/forms/jobs/${id}`);
  return res.data;
}

export async function uploadJobSource(
  jobId: string,
  file: File,
): Promise<FormDataSource> {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 300));
    const src: FormDataSource = {
      id: mockId("src"),
      job_id: jobId,
      kind: "user_upload",
      nas_file_id: null,
      upload_path: `/mock/uploads/${file.name}`,
      nas_chunk_ids: null,
      extracted_text: `[mock] ${file.name} 텍스트 추출 결과`,
      display_name: file.name,
      created_at: nowIso(),
    };
    const arr = mockStore.sources.get(jobId) ?? [];
    arr.push(src);
    mockStore.sources.set(jobId, arr);
    return src;
  }
  const fd = new FormData();
  fd.append("file", file);
  const res = await api.post<FormDataSource>(
    `/api/forms/jobs/${jobId}/sources/upload`,
    fd,
    { headers: { "Content-Type": "multipart/form-data" } },
  );
  return res.data;
}

export async function addNasSourcesToJob(
  jobId: string,
  nasFileIds: string[],
): Promise<FormDataSource[]> {
  if (MOCK_ENABLED) {
    const created: FormDataSource[] = nasFileIds.map((fid) => ({
      id: mockId("src"),
      job_id: jobId,
      kind: "nas_file" as const,
      nas_file_id: fid,
      upload_path: null,
      nas_chunk_ids: [],
      extracted_text: null,
      display_name: `NAS 파일 ${fid.slice(0, 6)}`,
      created_at: nowIso(),
    }));
    const arr = mockStore.sources.get(jobId) ?? [];
    arr.push(...created);
    mockStore.sources.set(jobId, arr);
    return created;
  }
  const res = await api.post<FormDataSource[]>(
    `/api/forms/jobs/${jobId}/sources/nas`,
    { nas_file_ids: nasFileIds },
  );
  return res.data;
}

export async function runJobMapping(jobId: string): Promise<FormMapping[]> {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 800));
    const job = mockStore.jobs.get(jobId);
    if (!job?.template_id) throw new Error("job/template missing (mock)");
    const tpl = mockStore.templates.get(job.template_id);
    if (!tpl) throw new Error("template not found (mock)");
    const sources = mockStore.sources.get(jobId) ?? [];
    const mappings = buildMockMappings(tpl, jobId, sources);
    mockStore.mappings.set(jobId, mappings);
    mockStore.jobs.set(jobId, { ...job, status: "reviewing" });
    return mappings;
  }
  const res = await api.post<FormMapping[]>(`/api/forms/jobs/${jobId}/run_mapping`);
  return res.data;
}

export async function patchJobMapping(
  jobId: string,
  variableKey: string,
  body: { value?: string | null; confirmed?: boolean; manual_override?: boolean },
): Promise<FormMapping> {
  if (MOCK_ENABLED) {
    const arr = mockStore.mappings.get(jobId) ?? [];
    const idx = arr.findIndex((m) => m.variable_key === variableKey);
    if (idx < 0) throw new Error("mapping not found (mock)");
    const next: FormMapping = {
      ...arr[idx],
      ...body,
      manual_override: body.manual_override ?? true,
      updated_at: nowIso(),
    };
    arr[idx] = next;
    mockStore.mappings.set(jobId, arr);
    return next;
  }
  const res = await api.patch<FormMapping>(
    `/api/forms/jobs/${jobId}/mappings/${encodeURIComponent(variableKey)}`,
    body,
  );
  return res.data;
}

export async function regenerateJobMapping(
  jobId: string,
  variableKey: string,
  feedback?: string,
): Promise<FormMapping> {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 500));
    const arr = mockStore.mappings.get(jobId) ?? [];
    const idx = arr.findIndex((m) => m.variable_key === variableKey);
    if (idx < 0) throw new Error("mapping not found (mock)");
    const next: FormMapping = {
      ...arr[idx],
      value: `재생성됨 (${feedback ?? "no comment"})`,
      llm_confidence: 0.85,
      manual_override: false,
      updated_at: nowIso(),
    };
    arr[idx] = next;
    mockStore.mappings.set(jobId, arr);
    return next;
  }
  const res = await api.post<FormMapping>(
    `/api/forms/jobs/${jobId}/regenerate`,
    { variable_key: variableKey, feedback },
  );
  return res.data;
}

export async function renderJobDocx(jobId: string): Promise<{ download_url: string }> {
  if (MOCK_ENABLED) {
    await new Promise((r) => setTimeout(r, 500));
    return { download_url: `/api/forms/jobs/${jobId}/download` };
  }
  const res = await api.post<{ download_url: string }>(`/api/forms/jobs/${jobId}/render`);
  return res.data;
}

export async function downloadJobOutput(jobId: string, filename: string): Promise<void> {
  if (MOCK_ENABLED) {
    // mock: 가상 다운로드 (alert 대신 console 미사용 — 사용자 안내는 호출처에서)
    return;
  }
  const res = await api.get<Blob>(`/api/forms/jobs/${jobId}/download`, {
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

export async function getJobRevisions(jobId: string): Promise<FormRevision[]> {
  if (MOCK_ENABLED) return [];
  const res = await api.get<FormRevision[]>(`/api/forms/jobs/${jobId}/revisions`);
  return res.data;
}
