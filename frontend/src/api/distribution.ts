import api from "./client";

/**
 * 신사업유통 모듈 — 텔레그램 페르소나 API 클라이언트 (T9 Phase A).
 *
 * 백엔드: `app/routers/distribution.py`
 *
 * 페르소나는 텔레그램 다계정 운영을 위한 단위. 어드민이 라벨/역할/표시명/폰
 * 번호와 my.telegram.org 발급 api_id/api_hash 를 등록한 뒤 SMS 2단계 인증으로
 * Telethon 세션을 로그인한다. 세션 파일은 백엔드에서 Fernet 으로 암호화 저장.
 */

export type PersonaRole = "vietnam_admin" | "domestic_admin";

export interface PersonaOut {
  id: string;
  account_label: string;
  role: PersonaRole;
  display_name: string;
  telegram_phone: string;
  telegram_user_id: number | null;
  has_credentials: boolean;
  is_logged_in: boolean;
  tone_profile: Record<string, unknown> | null;
  daily_msg_limit: number;
  active: boolean;
  warmup_until: string | null;
  last_login_at: string | null;
  created_at: string;
  updated_at: string | null;
}

export interface PersonaCreatePayload {
  account_label: string;
  role: PersonaRole;
  display_name: string;
  telegram_phone: string;
  api_id: string;
  api_hash: string;
  tone_profile?: Record<string, unknown> | null;
  daily_msg_limit?: number;
  warmup_days?: number;
}

export interface LoginInitResponse {
  phone_code_hash: string;
  sent_to_phone_masked: string;
}

export interface VerifyCodePayload {
  phone_code_hash: string;
  code: string;
  password?: string | null;
}

export interface VerifyCodeResponse {
  telegram_user_id: number;
  display_name: string;
  username: string | null;
}

const BASE = "/api/distribution";

/** 백엔드 응답 envelope — `{ personas: PersonaOut[] }`. */
interface ListPersonasResponse {
  personas: PersonaOut[];
}

export async function listPersonas(): Promise<PersonaOut[]> {
  const res = await api.get<ListPersonasResponse>(`${BASE}/personas`);
  return res.data.personas;
}

export async function createPersona(
  payload: PersonaCreatePayload,
): Promise<PersonaOut> {
  const res = await api.post<PersonaOut>(`${BASE}/personas`, payload);
  return res.data;
}

export async function deletePersona(id: string): Promise<void> {
  await api.delete(`${BASE}/personas/${id}`);
}

export async function logoutPersona(id: string): Promise<PersonaOut> {
  const res = await api.post<PersonaOut>(`${BASE}/personas/${id}/logout`);
  return res.data;
}

export async function initLogin(id: string): Promise<LoginInitResponse> {
  const res = await api.post<LoginInitResponse>(
    `${BASE}/personas/${id}/login-init`,
  );
  return res.data;
}

export async function verifyCode(
  id: string,
  payload: VerifyCodePayload,
): Promise<VerifyCodeResponse> {
  const res = await api.post<VerifyCodeResponse>(
    `${BASE}/personas/${id}/verify-code`,
    payload,
  );
  return res.data;
}

export const PERSONA_ROLE_LABEL: Record<PersonaRole, string> = {
  vietnam_admin: "베트남 어드민",
  domestic_admin: "국내 어드민",
};

export const PERSONA_ROLE_TAG_COLOR: Record<PersonaRole, string> = {
  vietnam_admin: "blue",
  domestic_admin: "green",
};

export const PERSONA_ROLE_OPTIONS: { value: PersonaRole; label: string }[] = [
  { value: "vietnam_admin", label: "베트남 어드민" },
  { value: "domestic_admin", label: "국내 어드민" },
];
