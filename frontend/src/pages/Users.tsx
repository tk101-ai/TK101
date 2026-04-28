import { useCallback, useEffect, useState } from "react";
import { Button, Form, Input, message, Modal, Select, Switch, Table, Tag } from "antd";
import { PlusOutlined, EditOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { getUsers, createUser, updateUser, type User } from "../api/users";
import {
  DEPARTMENT_OPTIONS,
  ROLE_OPTIONS,
  ROLE_TAG_COLOR,
  getDepartmentLabel,
  getRoleLabel,
  type RoleKey,
} from "../config/modules";

export default function Users() {
  const [data, setData] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModal, setCreateModal] = useState(false);
  const [editModal, setEditModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getUsers();
      setData(res.data);
    } catch {
      message.error("사용자 목록 조회 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreate = async (values: Record<string, string>) => {
    try {
      await createUser({
        email: values.email,
        password: values.password,
        name: values.name,
        department: values.department,
        role: values.role,
      });
      message.success("사용자 등록 완료");
      setCreateModal(false);
      createForm.resetFields();
      fetchData();
    } catch {
      message.error("등록 실패");
    }
  };

  const handleEdit = async (values: Record<string, unknown>) => {
    if (!editingUser) return;
    try {
      await updateUser(editingUser.id, {
        name: values.name as string,
        department: values.department as string,
        role: values.role as string,
        is_active: values.is_active as boolean,
      });
      message.success("사용자 정보 수정 완료");
      setEditModal(false);
      setEditingUser(null);
      editForm.resetFields();
      fetchData();
    } catch {
      message.error("수정 실패");
    }
  };

  const openEditModal = (record: User) => {
    setEditingUser(record);
    editForm.setFieldsValue({
      name: record.name,
      department: record.department,
      role: record.role,
      is_active: record.is_active,
    });
    setEditModal(true);
  };

  const columns: ColumnsType<User> = [
    { title: "이름", dataIndex: "name", width: 120 },
    { title: "이메일", dataIndex: "email", width: 200 },
    {
      title: "부서",
      dataIndex: "department",
      width: 130,
      render: (v: string) => getDepartmentLabel(v),
    },
    {
      title: "역할",
      dataIndex: "role",
      width: 100,
      render: (role: string) => (
        <Tag color={ROLE_TAG_COLOR[role as RoleKey] ?? "default"}>{getRoleLabel(role)}</Tag>
      ),
    },
    {
      title: "상태",
      dataIndex: "is_active",
      width: 80,
      render: (v: boolean) => (
        <Tag color={v ? "green" : "default"}>{v ? "활성" : "비활성"}</Tag>
      ),
    },
    {
      title: "가입일",
      dataIndex: "created_at",
      width: 120,
      render: (v: string) => dayjs(v).format("YYYY-MM-DD"),
    },
    {
      title: "",
      width: 60,
      render: (_, record) => (
        <Button type="link" icon={<EditOutlined />} onClick={() => openEditModal(record)} />
      ),
    },
  ];

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
        <h2>사용자 관리</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>
          사용자 추가
        </Button>
      </div>

      <Table columns={columns} dataSource={data} rowKey="id" loading={loading} size="middle" />

      <Modal
        title="사용자 추가"
        open={createModal}
        onCancel={() => setCreateModal(false)}
        onOk={() => createForm.submit()}
        okText="등록"
        cancelText="취소"
        destroyOnClose
      >
        <Form form={createForm} onFinish={handleCreate} layout="vertical" initialValues={{ role: "member" }}>
          <Form.Item name="name" label="이름" rules={[{ required: true, message: "이름을 입력하세요" }]}>
            <Input placeholder="이름" />
          </Form.Item>
          <Form.Item
            name="email"
            label="이메일"
            rules={[
              { required: true, message: "이메일을 입력하세요" },
              { type: "email", message: "올바른 이메일 형식을 입력하세요" },
            ]}
          >
            <Input placeholder="user@example.com" />
          </Form.Item>
          <Form.Item
            name="password"
            label="비밀번호"
            rules={[
              { required: true, message: "비밀번호를 입력하세요" },
              { min: 6, message: "6자 이상 입력하세요" },
            ]}
          >
            <Input.Password placeholder="비밀번호" />
          </Form.Item>
          <Form.Item name="department" label="부서" rules={[{ required: true, message: "부서를 선택하세요" }]}>
            <Select options={DEPARTMENT_OPTIONS} placeholder="부서 선택" />
          </Form.Item>
          <Form.Item name="role" label="역할" rules={[{ required: true, message: "역할을 선택하세요" }]}>
            <Select options={ROLE_OPTIONS} placeholder="역할 선택" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="사용자 수정"
        open={editModal}
        onCancel={() => { setEditModal(false); setEditingUser(null); }}
        onOk={() => editForm.submit()}
        okText="저장"
        cancelText="취소"
        destroyOnClose
      >
        <Form form={editForm} onFinish={handleEdit} layout="vertical">
          <Form.Item name="name" label="이름" rules={[{ required: true, message: "이름을 입력하세요" }]}>
            <Input placeholder="이름" />
          </Form.Item>
          <Form.Item name="department" label="부서" rules={[{ required: true, message: "부서를 선택하세요" }]}>
            <Select options={DEPARTMENT_OPTIONS} placeholder="부서 선택" />
          </Form.Item>
          <Form.Item name="role" label="역할" rules={[{ required: true, message: "역할을 선택하세요" }]}>
            <Select options={ROLE_OPTIONS} placeholder="역할 선택" />
          </Form.Item>
          <Form.Item name="is_active" label="활성 상태" valuePropName="checked">
            <Switch checkedChildren="활성" unCheckedChildren="비활성" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
