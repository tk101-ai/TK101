import api from "./client";

export interface TaxInvoice {
  id: string;
  invoice_type: string;
  invoice_number: string;
  issue_date: string;
  supplier_name: string;
  supplier_biz_no: string;
  buyer_name: string;
  buyer_biz_no: string;
  supply_amount: string;
  tax_amount: string;
  total_amount: string;
  matched_transaction_id: string | null;
  match_status: string;
  memo: string | null;
}

export interface TaxInvoiceFilter {
  invoice_type?: string;
  date_from?: string;
  date_to?: string;
  keyword?: string;
  match_status?: string;
}

export const getTaxInvoices = (params: TaxInvoiceFilter) =>
  api.get<TaxInvoice[]>("/api/tax-invoices", { params });

export const linkTransaction = (invoiceId: string, transactionId: string) =>
  api.patch<TaxInvoice>(`/api/tax-invoices/${invoiceId}/transaction`, {
    transaction_id: transactionId,
  });
