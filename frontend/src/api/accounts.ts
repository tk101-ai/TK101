import api from "./client";

/**
 * 은행 계좌 API 클라이언트 (재무 모듈 강화 Wave 3).
 *
 * 백엔드: `app/routers/accounts.py`
 * Wave 1·2: 모델·API에 account_type, currency, current_balance,
 *           last_synced_at, account_label, alias 6개 필드 추가.
 */

export type AccountType =
  | "general"
  | "foreign"
  | "loan"
  | "guaranteed_loan";

export type Currency =
  | "KRW"
  | "USD"
  | "EUR"
  | "JPY"
  | "CNY"
  | "HKD";

export const ACCOUNT_TYPE_LABEL: Record<AccountType, string> = {
  general: "일반",
  foreign: "외화",
  loan: "대출",
  guaranteed_loan: "기보보증",
};

export const ACCOUNT_TYPE_TAG_COLOR: Record<AccountType, string> = {
  general: "blue",
  foreign: "purple",
  loan: "orange",
  guaranteed_loan: "magenta",
};

export const CURRENCY_OPTIONS: { value: Currency; label: string }[] = [
  { value: "KRW", label: "KRW (원화)" },
  { value: "USD", label: "USD (미국 달러)" },
  { value: "EUR", label: "EUR (유로)" },
  { value: "JPY", label: "JPY (엔화)" },
  { value: "CNY", label: "CNY (위안화)" },
  { value: "HKD", label: "HKD (홍콩 달러)" },
];

export const ACCOUNT_TYPE_OPTIONS: { value: AccountType; label: string }[] = [
  { value: "general", label: "일반" },
  { value: "foreign", label: "외화" },
  { value: "loan", label: "대출" },
  { value: "guaranteed_loan", label: "기보보증" },
];

export interface Account {
  id: string;
  bank_name: string;
  account_number: string;
  account_holder: string;
  business_registration_no: string | null;
  is_active: boolean;
  account_type: AccountType | null;
  currency: Currency;
  current_balance: string | null;
  last_synced_at: string | null;
  account_label: string | null;
  alias: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface AccountCreate {
  bank_name: string;
  account_number: string;
  account_holder: string;
  business_registration_no?: string | null;
  account_type?: AccountType | null;
  currency?: Currency;
  account_label?: string | null;
  alias?: string | null;
}

export interface AccountUpdate {
  account_holder?: string;
  business_registration_no?: string | null;
  is_active?: boolean;
  account_type?: AccountType | null;
  account_label?: string | null;
  alias?: string | null;
}

export async function listAccounts(): Promise<Account[]> {
  const res = await api.get<Account[]>("/api/accounts");
  return res.data;
}

export async function getAccount(id: string): Promise<Account> {
  const res = await api.get<Account>(`/api/accounts/${id}`);
  return res.data;
}

export async function createAccount(body: AccountCreate): Promise<Account> {
  const res = await api.post<Account>("/api/accounts", body);
  return res.data;
}

export async function updateAccount(
  id: string,
  body: AccountUpdate,
): Promise<Account> {
  const res = await api.patch<Account>(`/api/accounts/${id}`, body);
  return res.data;
}

// 구 `getAccounts` 별칭은 H-5 정리 작업에서 제거되었습니다.
// 호출부는 `listAccounts()` 로 마이그레이션 되었습니다.
