import { useEffect, useState } from "react";
import { Button, Form, Input, message, Modal, Table, Tag } from "antd";
import { PlusOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import api from "../api/client";
import { getAccounts, type Account } from "../api/accounts";

export default function Accounts() {
  const [data, setData] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const [modal, setModal] = useState(false);
  const [form] = Form.useForm();

  const fetchData = async () => {
    setLoading(true);
    try {
      const res = await getAccounts();
      setData(res.data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, []);

  const handleCreate = async (values: Record<string, string>) => {
    try {
      await api.post("/api/accounts", values);
      message.success("계좌 등록 완료");
      setModal(false);
      form.resetFields();
      fetchData();
    } catch {
      message.error("등록 실패");
    }
  };

  const columns: ColumnsType<Account> = [
    { title: "은행", dataIndex: "bank_name", width: 120 },
    { title: "계좌번호", dataIndex: "account_number", width: 180 },
    { title: "예금주", dataIndex: "account_holder", width: 150 },
    { title: "사업자번호", dataIndex: "business_registration_no", width: 150 },
    {
      title: "상태",
      dataIndex: "is_active",
      width: 80,
      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "활성" : "비활성"}</Tag>,
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h2>계좌 관리</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setModal(true)}>
          계좌 등록
        </Button>
      </div>

      <Table columns={columns} dataSource={data} rowKey="id" loading={loading} size="middle" />

      <Modal title="계좌 등록" open={modal} onCancel={() => setModal(false)} onOk={() => form.submit()} okText="등록" cancelText="취소">
        <Form form={form} onFinish={handleCreate} layout="vertical">
          <Form.Item name="bank_name" label="은행명" rules={[{ required: true }]}>
            <Input placeholder="예: 국민은행" />
          </Form.Item>
          <Form.Item name="account_number" label="계좌번호" rules={[{ required: true }]}>
            <Input placeholder="000-000000-00-000" />
          </Form.Item>
          <Form.Item name="account_holder" label="예금주" rules={[{ required: true }]}>
            <Input placeholder="예금주명" />
          </Form.Item>
          <Form.Item name="business_registration_no" label="사업자등록번호">
            <Input placeholder="000-00-00000" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
