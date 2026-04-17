import api from "./client";

export interface Account {
  id: string;
  bank_name: string;
  account_number: string;
  account_holder: string;
  business_registration_no: string | null;
  is_active: boolean;
  created_at: string;
}

export const getAccounts = () => api.get<Account[]>("/api/accounts");
