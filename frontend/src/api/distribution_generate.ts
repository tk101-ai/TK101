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

export interface ScenarioBrief {
  id: string;
  name: string;
  trigger_event: string;
  sender_role: "domestic_admin" | "vietnam_admin";
  receiver_role: "domestic_admin" | "vietnam_admin";
}

interface ListScenariosResponse {
  items: ScenarioBrief[];
}

export async function listScenarios(): Promise<ScenarioBrief[]> {
  const res = await api.get<ListScenariosResponse>(`${BASE}/scenarios`);
  return res.data.items;
}

// ---------------------------------------------------------------------------
// 커스텀 생성 트리거
// ---------------------------------------------------------------------------

export interface GenerateCustomPayload {
  sender_persona_ids: string[];
  scenario_names: string[];
  period_label?: string | null;
  company_label?: string;
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
    },
  );
  return res.data;
}
