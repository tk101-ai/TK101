import api from "./client";

/**
 * 신사업유통 — 커스텀 생성 트리거 + 시나리오 조회 API (T9 Phase E-2).
 *
 * 백엔드:
 * - `app/routers/distribution_generate_v2.py` (POST /generate-custom)
 * - `app/routers/distribution_scenarios.py`   (GET  /scenarios)
 *
 * 기존 `api/distribution.ts` 와 분리: 모달 전용 신규 흐름이라 기존 PersonaCreate /
 * SessionList 등 다른 흐름에 영향이 가지 않도록 격리.
 */

const BASE = "/api/distribution";

// ---------------------------------------------------------------------------
// 시나리오 — 모달 선택용 슬림 응답
// ---------------------------------------------------------------------------

/** 대화 언어 (T9 — 2026-05-27). ko=한국어 | zh=간체 중국어. */
export type DistributionLanguage = "ko" | "zh";

export interface ScenarioBrief {
  id: string;
  name: string;
  trigger_event: string;
  sender_role: "domestic_admin" | "vietnam_admin";
  receiver_role: "domestic_admin" | "vietnam_admin";
  /** 시나리오 기본 언어. 모달 기본 언어 힌트로 사용. default 'ko'. */
  language?: DistributionLanguage;
  /** 첨부 권장 시나리오 여부. */
  attachment_required?: boolean;
  /** 사용자 자유 텍스트 지시 (있으면 사용자 작성 시나리오). */
  instruction?: string | null;
}

interface ListScenariosResponse {
  items: ScenarioBrief[];
}

export async function listScenarios(): Promise<ScenarioBrief[]> {
  const res = await api.get<ListScenariosResponse>(`${BASE}/scenarios`);
  return res.data.items;
}

// ---------------------------------------------------------------------------
// 사용자 작성 시나리오 생성 (저장형) — 자연어 지시 기반
// ---------------------------------------------------------------------------

export interface UserScenarioCreatePayload {
  name: string;
  instruction: string;
  sender_role?: "domestic_admin" | "vietnam_admin";
  receiver_role?: "domestic_admin" | "vietnam_admin";
  language?: DistributionLanguage;
  attachment_required?: boolean;
}

/** 자연어 지시 기반 사용자 시나리오 생성. 성공 시 picker 에 즉시 노출(active=True). */
export async function createUserScenario(
  payload: UserScenarioCreatePayload,
): Promise<ScenarioBrief> {
  const res = await api.post<ScenarioBrief>(`${BASE}/scenarios`, {
    name: payload.name,
    instruction: payload.instruction,
    sender_role: payload.sender_role ?? "domestic_admin",
    receiver_role: payload.receiver_role ?? "vietnam_admin",
    language: payload.language ?? "zh",
    attachment_required: payload.attachment_required ?? false,
  });
  return res.data;
}

// ---------------------------------------------------------------------------
// 커스텀 생성 트리거
// ---------------------------------------------------------------------------

export type TimingProfile = "short" | "normal" | "varied";

export interface GenerateCustomPayload {
  sender_persona_ids: string[];
  scenario_names: string[];
  period_label?: string | null;
  company_label?: string;
  /** 메시지 간격 분포 (T9 — 2026-05-26). default 'normal'. */
  timing_profile?: TimingProfile;
  /** 대화 언어 (T9 — 2026-05-27). default 'ko'. */
  language?: DistributionLanguage;
  /** 즉석 지시(저장 안 함) — 있으면 숨김 시나리오 자동 생성 후 사용. */
  ad_hoc_instruction?: string;
}

export interface GenerateCustomResult {
  sessions_created: string[];
  skipped: string[];
  errors: string[];
  used_period_label: string | null;
}

/**
 * 사용자가 명시한 (페르소나 × 시나리오 × 주차) 조합으로 세션 생성.
 *
 * - 발신 페르소나는 한국 어드민(domestic_admin) 만 허용. 그 외 역할은 백엔드가 errors 에 기록.
 * - 베트남 어드민은 백엔드가 활성 1명 자동 선택.
 * - period_label 미지정 시 최신 주차 weekly_summary 사용.
 */
export async function generateCustom(
  payload: GenerateCustomPayload,
): Promise<GenerateCustomResult> {
  const res = await api.post<GenerateCustomResult>(
    `${BASE}/generate-custom`,
    {
      sender_persona_ids: payload.sender_persona_ids,
      scenario_names: payload.scenario_names,
      period_label: payload.period_label ?? null,
      company_label: payload.company_label ?? "래더엑스",
      timing_profile: payload.timing_profile ?? "normal",
      language: payload.language ?? "ko",
      ad_hoc_instruction: payload.ad_hoc_instruction ?? null,
    },
  );
  return res.data;
}
