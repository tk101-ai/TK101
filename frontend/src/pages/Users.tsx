import { useCallback, useEffect, useState } from "react";
import { Alert, Button, Form, Input, message, Modal, Popconfirm, Select, Switch, Table, Tag } from "antd";
import { PlusOutlined, EditOutlined, CheckOutlined, CloseOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import {
  getUsers,
  createUser,
  updateUser,
  approveUser,
  rejectUser,
  type User,
} from "../api/users";
import {
  DEPARTMENT_OPTIONS,
  ROLE_OPTIONS,
  ROLE_TAG_COLOR,
  getDepartmentLabel,
  getRoleLabel,
  type RoleKey,
} from "../config/modules";

const STATUS_META: Record<string, { color: string; label: string }> = {
  pending: { color: "orange", label: "승인대기" },
  active: { color: "green", label: "활성" },
  rejected: { color: "red", label: "거절" },
};

export default function Users() {
  const [data, setData] = useState<User[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModal, setCreateModal] = useState(false);
  const [editModal, setEditModal] = useState(false);
  const [approveModal, setApproveModal] = useState(false);
  const [target, setTarget] = useState<User | null>(null);
  const [createForm] = Form.useForm();
  const [editForm] = Form.useForm();
  const [approveForm] = Form.useForm();

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
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchData();
  }, [fetchData]);

  const pending = data.filter((u) => u.status === "pending");

  const handleCreate = async (values: Record<string, unknown>) => {
    try {
      await createUser({
        email: values.email as string,
        password: values.password as string,
        name: values.name as string,
        department: values.department as string,
        role: values.role as string,
        departments: values.departments as string[] | undefined,
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
    if (!target) return;
    try {
      await updateUser(target.id, {
        name: values.name as string,
        department: values.department as string,
        role: values.role as string,
        is_active: values.is_active as boolean,
        departments: values.departments as string[] | undefined,
      });
      message.success("사용자 정보 수정 완료");
      setEditModal(false);
      setTarget(null);
      editForm.resetFields();
      fetchData();
    } catch {
      message.error("수정 실패");
    }
  };

  const handleApprove = async (values: Record<string, unknown>) => {
    if (!target) return;
    try {
      await approveUser(target.id, {
        department: values.department as string,
        role: values.role as string,
        departments: values.departments as string[] | undefined,
      });
      message.success(`${target.name} 승인 완료`);
      setApproveModal(false);
      setTarget(null);
      approveForm.resetFields();
      fetchData();
    } catch {
      message.error("승인 실패");
    }
  };

  const handleReject = async (record: User) => {
    try {
      await rejectUser(record.id);
      message.success(`${record.name} 거절 처리`);
      fetchData();
    } catch {
      message.error("거절 실패");
    }
  };

  const openEdit = (record: User) => {
    setTarget(record);
    editForm.setFieldsValue({
      name: record.name,
      department: record.department,
      role: record.role,
      is_active: record.is_active,
      departments: record.departments ?? [],
    });
    setEditModal(true);
  };

  const openApprove = (record: User) => {
    setTarget(record);
    approveForm.setFieldsValue({
      department: record.department,
      role: "member",
      departments: record.departments ?? [],
    });
    setApproveModal(true);
  };

  const columns: ColumnsType<User> = [
    { title: "이름", dataIndex: "name", width: 110 },
    { title: "이메일", dataIndex: "email", width: 200 },
    {
      title: "부서",
      dataIndex: "departments",
      width: 200,
      render: (depts: string[] | undefined, record) => {
        const list = depts && depts.length ? depts : [record.department];
        return list.map((d) => <Tag key={d}>{getDepartmentLabel(d)}</Tag>);
      },
    },
    {
      title: "역할",
      dataIndex: "role",
      width: 90,
      render: (role: string) => (
        <Tag color={ROLE_TAG_COLOR[role as RoleKey] ?? "default"}>{getRoleLabel(role)}</Tag>
      ),
    },
    {
      title: "상태",
      dataIndex: "status",
      width: 90,
      render: (s: string) => {
        const meta = STATUS_META[s] ?? { color: "default", label: s };
        return <Tag color={meta.color}>{meta.label}</Tag>;
      },
    },
    {
      title: "가입일",
      dataIndex: "created_at",
      width: 110,
      render: (v: string) => dayjs(v).format("YYYY-MM-DD"),
    },
    {
      title: "",
      width: 150,
      render: (_, record) =>
        record.status === "pending" ? (
          <>
            <Button type="link" size="small" icon={<CheckOutlined />} onClick={() => openApprove(record)}>
              승인
            </Button>
            <Popconfirm title="가입을 거절할까요?" onConfirm={() => handleReject(record)} okText="거절" cancelText="취소">
              <Button type="link" size="small" danger icon={<CloseOutlined />}>
                거절
              </Button>
            </Popconfirm>
          </>
        ) : (
          <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(record)} />
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

      {pending.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message={`승인 대기 ${pending.length}건 — 가입 신청한 직원을 검토 후 승인/거절하세요.`}
        />
      )}

      <Table columns={columns} dataSource={data} rowKey="id" loading={loading} size="middle" />

      {/* 생성 */}
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
          <Form.Item name="name" label="이름" rules={[{ required: true }]}>
            <Input placeholder="이름" />
          </Form.Item>
          <Form.Item name="email" label="이메일" rules={[{ required: true }, { type: "email" }]}>
            <Input placeholder="user@tk101global.com" />
          </Form.Item>
          <Form.Item name="password" label="비밀번호" rules={[{ required: true }, { min: 8, message: "8자 이상" }]}>
            <Input.Password placeholder="비밀번호 (8자 이상)" />
          </Form.Item>
          <Form.Item name="department" label="주 부서" rules={[{ required: true }]}>
            <Select options={DEPARTMENT_OPTIONS} placeholder="주 부서" />
          </Form.Item>
          <Form.Item name="departments" label="추가 부서 (팀장급 다중 소속)" extra="비워두면 주 부서만 적용">
            <Select mode="multiple" options={DEPARTMENT_OPTIONS} placeholder="추가 부서(선택)" allowClear />
          </Form.Item>
          <Form.Item name="role" label="역할" rules={[{ required: true }]}>
            <Select options={ROLE_OPTIONS} placeholder="역할" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 승인 */}
      <Modal
        title={`가입 승인 — ${target?.name ?? ""}`}
        open={approveModal}
        onCancel={() => { setApproveModal(false); setTarget(null); }}
        onOk={() => approveForm.submit()}
        okText="승인"
        cancelText="취소"
        destroyOnClose
      >
        <p style={{ color: "#888" }}>
          {target?.email} — 신청 부서: {getDepartmentLabel(target?.department ?? "")}
        </p>
        <Form form={approveForm} onFinish={handleApprove} layout="vertical">
          <Form.Item name="department" label="주 부서" rules={[{ required: true }]}>
            <Select options={DEPARTMENT_OPTIONS} placeholder="주 부서" />
          </Form.Item>
          <Form.Item name="departments" label="추가 부서 (다중 소속)">
            <Select mode="multiple" options={DEPARTMENT_OPTIONS} placeholder="추가 부서(선택)" allowClear />
          </Form.Item>
          <Form.Item name="role" label="역할" rules={[{ required: true }]}>
            <Select options={ROLE_OPTIONS} placeholder="역할" />
          </Form.Item>
        </Form>
      </Modal>

      {/* 수정 */}
      <Modal
        title="사용자 수정"
        open={editModal}
        onCancel={() => { setEditModal(false); setTarget(null); }}
        onOk={() => editForm.submit()}
        okText="저장"
        cancelText="취소"
        destroyOnClose
      >
        <Form form={editForm} onFinish={handleEdit} layout="vertical">
          <Form.Item name="name" label="이름" rules={[{ required: true }]}>
            <Input placeholder="이름" />
          </Form.Item>
          <Form.Item name="department" label="주 부서" rules={[{ required: true }]}>
            <Select options={DEPARTMENT_OPTIONS} placeholder="주 부서" />
          </Form.Item>
          <Form.Item name="departments" label="추가 부서 (다중 소속)">
            <Select mode="multiple" options={DEPARTMENT_OPTIONS} placeholder="추가 부서(선택)" allowClear />
          </Form.Item>
          <Form.Item name="role" label="역할" rules={[{ required: true }]}>
            <Select options={ROLE_OPTIONS} placeholder="역할" />
          </Form.Item>
          <Form.Item name="is_active" label="활성 상태" valuePropName="checked">
            <Switch checkedChildren="활성" unCheckedChildren="비활성" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
