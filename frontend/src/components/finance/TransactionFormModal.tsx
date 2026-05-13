import { useEffect } from "react";
import {
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Select,
} from "antd";
import dayjs, { Dayjs } from "dayjs";
import type { Account } from "../../api/accounts";
import type {
  TransactionCreate,
  TransactionType,
} from "../../api/transactions";
import type { CategoryRead } from "../../api/categories";

interface TransactionFormValues {
  account_id: string;
  transaction_date: Dayjs;
  transaction_type: TransactionType;
  amount: number;
  balance?: number;
  counterpart_name?: string;
  description?: string;
  memo?: string;
  category_id?: string;
  tags?: string[];
}

interface TransactionFormModalProps {
  open: boolean;
  loading?: boolean;
  accounts: Account[];
  categories: CategoryRead[];
  defaultAccountId?: string;
  onCancel: () => void;
  onSubmit: (body: TransactionCreate) => Promise<void> | void;
}

// 수동 거래 등록 모달. 백엔드: POST /api/transactions
export default function TransactionFormModal({
  open,
  loading,
  accounts,
  categories,
  defaultAccountId,
  onCancel,
  onSubmit,
}: TransactionFormModalProps) {
  const [form] = Form.useForm<TransactionFormValues>();

  useEffect(() => {
    if (open) {
      form.resetFields();
      form.setFieldsValue({
        transaction_date: dayjs(),
        transaction_type: "deposit",
        account_id: defaultAccountId,
      });
    }
  }, [open, defaultAccountId, form]);

  const handleOk = async () => {
    const values = await form.validateFields();
    const body: TransactionCreate = {
      account_id: values.account_id,
      transaction_date: values.transaction_date.format("YYYY-MM-DD"),
      transaction_type: values.transaction_type,
      amount: values.amount,
      balance: values.balance,
      counterpart_name: values.counterpart_name?.trim() || undefined,
      description: values.description?.trim() || undefined,
      memo: values.memo?.trim() || undefined,
      category_id: values.category_id || undefined,
      tags: values.tags && values.tags.length > 0 ? values.tags : undefined,
    };
    await onSubmit(body);
  };

  return (
    <Modal
      title="거래 수동 등록"
      open={open}
      onCancel={onCancel}
      onOk={handleOk}
      confirmLoading={loading}
      okText="등록"
      cancelText="취소"
      destroyOnClose
      width={560}
    >
      <Form form={form} layout="vertical">
        <Form.Item
          name="account_id"
          label="계좌"
          rules={[{ required: true, message: "계좌를 선택하세요" }]}
        >
          <Select
            placeholder="계좌 선택"
            options={accounts.map((a) => ({
              label: `${a.bank_name} ${a.account_number.slice(-4)}`,
              value: a.id,
            }))}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>
        <Form.Item
          name="transaction_date"
          label="거래일"
          rules={[{ required: true, message: "거래일을 선택하세요" }]}
        >
          <DatePicker style={{ width: "100%" }} format="YYYY-MM-DD" />
        </Form.Item>
        <Form.Item
          name="transaction_type"
          label="구분"
          rules={[{ required: true }]}
        >
          <Select
            options={[
              { label: "입금", value: "deposit" },
              { label: "출금", value: "withdrawal" },
            ]}
          />
        </Form.Item>
        <Form.Item
          name="amount"
          label="금액 (원)"
          rules={[{ required: true, message: "금액을 입력하세요" }]}
        >
          <InputNumber
            style={{ width: "100%" }}
            min={0}
            step={1000}
            formatter={(v) => (v == null ? "" : `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ","))}
          />
        </Form.Item>
        <Form.Item name="balance" label="잔액 (원)">
          <InputNumber
            style={{ width: "100%" }}
            step={1000}
            formatter={(v) => (v == null ? "" : `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ","))}
          />
        </Form.Item>
        <Form.Item name="counterpart_name" label="거래처명">
          <Input placeholder="예: 홍길동, ㈜TK101" />
        </Form.Item>
        <Form.Item name="description" label="적요">
          <Input placeholder="입출금 적요" />
        </Form.Item>
        <Form.Item name="category_id" label="카테고리">
          <Select
            placeholder="카테고리 선택"
            allowClear
            options={categories.map((c) => ({ label: c.name, value: c.id }))}
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>
        <Form.Item name="tags" label="태그">
          <Select mode="tags" placeholder="태그 입력 후 Enter" tokenSeparators={[","]} />
        </Form.Item>
        <Form.Item name="memo" label="메모">
          <Input.TextArea rows={2} placeholder="특이사항" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
