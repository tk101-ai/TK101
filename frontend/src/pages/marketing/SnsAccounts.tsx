import { useCallback, useEffect, useState } from "react";
import { Button, Form, Input, message, Modal, Select, Space, Switch, Table, Tag } from "antd";
import { EditOutlined, PlusOutlined, SyncOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import {
  createAccount,
  getLanguageLabel,
  getPlatformLabel,
  LANGUAGE_OPTIONS,
  listAccounts,
  PLATFORM_OPTIONS,
  triggerCollect,
  updateAccount,
  type Language,
  type Platform,
  type SnsAccount,
} from "../../api/sns";
import { useAuth } from "../../hooks/useAuth";

const COLLECTABLE_PLATFORMS: ReadonlySet<Platform> = new Set<Platform>(["youtube"]);

interface AccountFormValues {
  platform: Platform;
  language: Language;
  handle?: string;
  page_url?: string;
  external_id?: string;
  is_active: boolean;
}

export default function SnsAccounts() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [data, setData] = useState<SnsAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [createModal, setCreateModal] = useState(false);
  const [editModal, setEditModal] = useState(false);
  const [editing, setEditing] = useState<SnsAccount | null>(null);
  const [createForm] = Form.useForm<AccountFormValues>();
  const [editForm] = Form.useForm<AccountFormValues>();
  const [collectingId, setCollectingId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listAccounts();
      setData(res.data);
    } catch {
      message.error("계정 목록 조회 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleCreate = async (values: AccountFormValues) => {
    try {
      await createAccount({
        platform: values.platform,
        language: values.language,
        handle: values.handle ?? null,
        page_url: values.page_url ?? null,
        external_id: values.external_id ?? null,
        is_active: values.is_active ?? true,
      });
      message.success("계정 등록 완료");
      setCreateModal(false);
      createForm.resetFields();
      fetchData();
    } catch {
      message.error("등록 실패");
    }
  };

  const handleEdit = async (values: AccountFormValues) => {
    if (!editing) return;
    try {
      await updateAccount(editing.id, {
        platform: values.platform,
        language: values.language,
        handle: values.handle ?? null,
        page_url: values.page_url ?? null,
        external_id: values.external_id ?? null,
        is_active: values.is_active,
      });
      message.success("계정 정보 수정 완료");
      setEditModal(false);
      setEditing(null);
      editForm.resetFields();
      fetchData();
    } catch {
      message.error("수정 실패");
    }
  };

  const handleCollect = async (record: SnsAccount) => {
    setCollectingId(record.id);
    try {
      const res = await triggerCollect(record.id);
      const { posts_added, posts_updated, snapshots_added, snapshots_updated } = res.data;
      message.success(
        `수집 완료 — 게시물 ${posts_added}건 추가/${posts_updated}건 갱신, 팔로워 스냅샷 ${
          snapshots_added + snapshots_updated
        }건`,
      );
      fetchData();
    } catch (err) {
      const detail =
        err && typeof err === "object" && "response" in err
          ? (err as { response?: { data?: { detail?: string } } }).response?.data?.detail
          : null;
      message.error(detail ? `수집 실패: ${detail}` : "수집 실패");
    } finally {
      setCollectingId(null);
    }
  };

  const openEdit = (record: SnsAccount) => {
    setEditing(record);
    editForm.setFieldsValue({
      platform: record.platform,
      language: record.language,
      handle: record.handle ?? undefined,
      page_url: record.page_url ?? undefined,
      external_id: record.external_id ?? undefined,
      is_active: record.is_active,
    });
    setEditModal(true);
  };

  const columns: ColumnsType<SnsAccount> = [
    {
      title: "플랫폼",
      dataIndex: "platform",
      width: 110,
      render: (v: string) => <Tag color="blue">{getPlatformLabel(v)}</Tag>,
    },
    {
      title: "어권",
      dataIndex: "language",
      width: 90,
      render: (v: string) => <Tag>{getLanguageLabel(v)}</Tag>,
    },
    { title: "핸들", dataIndex: "handle", width: 180, render: (v: string | null) => v ?? "-" },
    {
      title: "페이지 URL",
      dataIndex: "page_url",
      ellipsis: true,
      render: (v: string | null) =>
        v ? (
          <a href={v} target="_blank" rel="noreferrer">
            {v}
          </a>
        ) : (
          "-"
        ),
    },
    {
      title: "외부 ID",
      dataIndex: "external_id",
      width: 160,
      render: (v: string | null) => v ?? "-",
    },
    {
      title: "상태",
      dataIndex: "is_active",
      width: 80,
      render: (v: boolean) => <Tag color={v ? "green" : "default"}>{v ? "활성" : "비활성"}</Tag>,
    },
    {
      title: "등록일",
      dataIndex: "created_at",
      width: 120,
      render: (v: string) => dayjs(v).format("YYYY-MM-DD"),
    },
    ...(isAdmin
      ? [
          {
            title: "",
            width: 160,
            render: (_: unknown, record: SnsAccount) => (
              <Space size="small">
                <Button
                  type="primary"
                  size="small"
                  icon={<SyncOutlined spin={collectingId === record.id} />}
                  loading={collectingId === record.id}
                  disabled={!COLLECTABLE_PLATFORMS.has(record.platform) || !record.is_active}
                  onClick={() => handleCollect(record)}
                  title={
                    !COLLECTABLE_PLATFORMS.has(record.platform)
                      ? "이 플랫폼은 자동 수집을 아직 지원하지 않습니다"
                      : "지금 수집"
                  }
                >
                  수집
                </Button>
                <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(record)} />
              </Space>
            ),
          },
        ]
      : []),
  ];

  return (
    <div style={{ maxWidth: 1200 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 28 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>SNS 계정</h2>
        {isAdmin && (
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>
            계정 추가
          </Button>
        )}
      </div>

      <Table columns={columns} dataSource={data} rowKey="id" loading={loading} size="middle" />

      <Modal
        title="계정 추가"
        open={createModal}
        onCancel={() => setCreateModal(false)}
        onOk={() => createForm.submit()}
        okText="등록"
        cancelText="취소"
        destroyOnClose
      >
        <Form
          form={createForm}
          onFinish={handleCreate}
          layout="vertical"
          initialValues={{ is_active: true }}
        >
          <Form.Item name="platform" label="플랫폼" rules={[{ required: true, message: "플랫폼을 선택하세요" }]}>
            <Select options={PLATFORM_OPTIONS} placeholder="플랫폼 선택" />
          </Form.Item>
          <Form.Item name="language" label="어권" rules={[{ required: true, message: "어권을 선택하세요" }]}>
            <Select options={LANGUAGE_OPTIONS} placeholder="어권 선택" />
          </Form.Item>
          <Form.Item name="handle" label="핸들">
            <Input placeholder="@계정명" />
          </Form.Item>
          <Form.Item name="page_url" label="페이지 URL">
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item name="external_id" label="외부 ID">
            <Input placeholder="플랫폼 내부 ID" />
          </Form.Item>
          <Form.Item name="is_active" label="활성 상태" valuePropName="checked">
            <Switch checkedChildren="활성" unCheckedChildren="비활성" />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="계정 수정"
        open={editModal}
        onCancel={() => {
          setEditModal(false);
          setEditing(null);
        }}
        onOk={() => editForm.submit()}
        okText="저장"
        cancelText="취소"
        destroyOnClose
      >
        <Form form={editForm} onFinish={handleEdit} layout="vertical">
          <Form.Item name="platform" label="플랫폼" rules={[{ required: true, message: "플랫폼을 선택하세요" }]}>
            <Select options={PLATFORM_OPTIONS} placeholder="플랫폼 선택" />
          </Form.Item>
          <Form.Item name="language" label="어권" rules={[{ required: true, message: "어권을 선택하세요" }]}>
            <Select options={LANGUAGE_OPTIONS} placeholder="어권 선택" />
          </Form.Item>
          <Form.Item name="handle" label="핸들">
            <Input placeholder="@계정명" />
          </Form.Item>
          <Form.Item name="page_url" label="페이지 URL">
            <Input placeholder="https://..." />
          </Form.Item>
          <Form.Item name="external_id" label="외부 ID">
            <Input placeholder="플랫폼 내부 ID" />
          </Form.Item>
          <Form.Item name="is_active" label="활성 상태" valuePropName="checked">
            <Switch checkedChildren="활성" unCheckedChildren="비활성" />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
