import api from "./client";

export interface Transaction {
  id: string;
  account_id: string;
  transaction_date: string;
  amount: string;
  balance: string | null;
  counterpart_name: string | null;
  description: string | null;
  transaction_type: string;
  matched_transaction_id: string | null;
  match_status: string;
  memo: string | null;
  created_at: string;
}

export interface TransactionFilter {
  account_id?: string;
  date_from?: string;
  date_to?: string;
  transaction_type?: string;
  match_status?: string;
  keyword?: string;
  limit?: number;
  offset?: number;
}

export const getTransactions = (params: TransactionFilter) =>
  api.get<Transaction[]>("/api/transactions", { params });

export const updateMemo = (id: string, memo: string) =>
  api.patch<Transaction>(`/api/transactions/${id}/memo`, { memo });

export const downloadExcel = (params: TransactionFilter) =>
  api.get("/api/transactions/download", { params, responseType: "blob" });

export const uploadTransactions = (accountId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return api.post("/api/uploads/transactions", form, {
    params: { account_id: accountId },
  });
};

export const runMatching = () => api.post("/api/matching/run");
export const runReconcile = () => api.post("/api/matching/reconcile");
