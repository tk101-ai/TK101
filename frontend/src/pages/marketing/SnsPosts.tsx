import { useCallback, useEffect, useState } from "react";
import {
  Button,
  DatePicker,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Select,
  Space,
  Table,
  Tag,
} from "antd";
import { EditOutlined, LinkOutlined, PlusOutlined, SearchOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs, { type Dayjs } from "dayjs";
import {
  CONTENT_TYPE_OPTIONS,
  createPost,
  getContentTypeLabel,
  getPlatformLabel,
  listAccounts,
  listPosts,
  updatePost,
  type CreatePostRequest,
  type PostFilter,
  type SnsAccount,
  type SnsPost,
} from "../../api/sns";

const { RangePicker } = DatePicker;

const PRODUCER_OPTIONS = [
  { value: "서울시제공", label: "서울시제공" },
  { value: "TK제작", label: "TK제작" },
];

interface PostFormValues {
  account_id: string;
  posted_at: Dayjs;
  title?: string;
  content_type?: string;
  producer?: string;
  view_count?: number | null;
  reach_count?: number | null;
  comment_count?: number | null;
  like_count?: number | null;
  share_count?: number | null;
  save_count?: number | null;
  url?: string;
}

function buildAccountLabel(account: SnsAccount): string {
  const handle = account.handle ?? account.external_id ?? account.id.slice(0, 8);
  return `${getPlatformLabel(account.platform)} · ${handle}`;
}

export default function SnsPosts() {
  const [data, setData] = useState<SnsPost[]>([]);
  const [accounts, setAccounts] = useState<SnsAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<PostFilter>({ limit: 50, offset: 0 });
  const [keyword, setKeyword] = useState("");
  const [createModal, setCreateModal] = useState(false);
  const [editModal, setEditModal] = useState(false);
  const [editing, setEditing] = useState<SnsPost | null>(null);
  const [createForm] = Form.useForm<PostFormValues>();
  const [editForm] = Form.useForm<PostFormValues>();

  const fetchAccounts = useCallback(async () => {
    try {
      const res = await listAccounts();
      setAccounts(res.data);
    } catch {
      message.error("계정 목록 조회 실패");
    }
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listPosts(filters);
      setData(res.data);
    } catch {
      message.error("콘텐츠 목록 조회 실패");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const accountMap = new Map(accounts.map((a) => [a.id, a]));

  const handleSearch = () => {
    setFilters((f) => ({ ...f, keyword: keyword || undefined, offset: 0 }));
  };

  const handleCreate = async (values: PostFormValues) => {
    try {
      const payload: CreatePostRequest = {
        account_id: values.account_id,
        posted_at: values.posted_at.format("YYYY-MM-DD"),
        title: values.title ?? null,
        content_type: values.content_type ?? null,
        producer: values.producer ?? null,
        view_count: values.view_count ?? null,
        reach_count: values.reach_count ?? null,
        comment_count: values.comment_count ?? null,
        like_count: values.like_count ?? null,
        share_count: values.share_count ?? null,
        save_count: values.save_count ?? null,
        url: values.url ?? null,
      };
      await createPost(payload);
      message.success("콘텐츠 등록 완료");
      setCreateModal(false);
      createForm.resetFields();
      fetchData();
    } catch {
      message.error("등록 실패");
    }
  };

  const handleEdit = async (values: PostFormValues) => {
    if (!editing) return;
    try {
      await updatePost(editing.id, {
        account_id: values.account_id,
        posted_at: values.posted_at.format("YYYY-MM-DD"),
        title: values.title ?? null,
        content_type: values.content_type ?? null,
        producer: values.producer ?? null,
        view_count: values.view_count ?? null,
        reach_count: values.reach_count ?? null,
        comment_count: values.comment_count ?? null,
        like_count: values.like_count ?? null,
        share_count: values.share_count ?? null,
        save_count: values.save_count ?? null,
        url: values.url ?? null,
      });
      message.success("콘텐츠 수정 완료");
      setEditModal(false);
      setEditing(null);
      editForm.resetFields();
      fetchData();
    } catch {
      message.error("수정 실패");
    }
  };

  const openEdit = (record: SnsPost) => {
    setEditing(record);
    editForm.setFieldsValue({
      account_id: record.account_id,
      posted_at: dayjs(record.posted_at),
      title: record.title ?? undefined,
      content_type: record.content_type ?? undefined,
      producer: record.producer ?? undefined,
      view_count: record.view_count,
      reach_count: record.reach_count,
      comment_count: record.comment_count,
      like_count: record.like_count,
      share_count: record.share_count,
      save_count: record.save_count,
      url: record.url ?? undefined,
    });
    setEditModal(true);
  };

  const columns: ColumnsType<SnsPost> = [
    {
      title: "배포일",
      dataIndex: "posted_at",
      width: 110,
      sorter: (a, b) => a.posted_at.localeCompare(b.posted_at),
    },
    {
      title: "계정",
      dataIndex: "account_id",
      width: 200,
      render: (id: string) => {
        const acct = accountMap.get(id);
        return acct ? buildAccountLabel(acct) : id.slice(0, 8);
      },
    },
    { title: "제목", dataIndex: "title", ellipsis: true },
    {
      title: "형태",
      dataIndex: "content_type",
      width: 90,
      render: (v: string | null) => (v ? <Tag color="purple">{getContentTypeLabel(v)}</Tag> : "-"),
    },
    {
      title: "조회수",
      dataIndex: "view_count",
      width: 110,
      align: "right" as const,
      render: (v: number | null) => (v != null ? v.toLocaleString("ko-KR") : "-"),
    },
    {
      title: "참여",
      dataIndex: "total_engagement",
      width: 110,
      align: "right" as const,
      render: (v: number | null) => (v != null ? v.toLocaleString("ko-KR") : "-"),
    },
    {
      title: "링크",
      dataIndex: "url",
      width: 70,
      render: (v: string | null) =>
        v ? (
          <Button type="link" size="small" icon={<LinkOutlined />} href={v} target="_blank" />
        ) : (
          "-"
        ),
    },
    {
      title: "",
      width: 60,
      render: (_, record) => (
        <Button type="link" icon={<EditOutlined />} onClick={() => openEdit(record)} />
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 1200 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 28 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700, letterSpacing: "-0.02em" }}>SNS 콘텐츠</h2>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateModal(true)}>
          콘텐츠 추가
        </Button>
      </div>

      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          placeholder="계정 선택"
          allowClear
          style={{ width: 220 }}
          onChange={(v) => setFilters((f) => ({ ...f, account_id: v, offset: 0 }))}
          options={accounts.map((a) => ({ label: buildAccountLabel(a), value: a.id }))}
        />
        <RangePicker
          onChange={(_, dates) =>
            setFilters((f) => ({
              ...f,
              date_from: dates?.[0] || undefined,
              date_to: dates?.[1] || undefined,
              offset: 0,
            }))
          }
        />
        <Select
          placeholder="콘텐츠 형태"
          allowClear
          style={{ width: 130 }}
          onChange={(v) => setFilters((f) => ({ ...f, content_type: v, offset: 0 }))}
          options={CONTENT_TYPE_OPTIONS}
        />
        <Input
          placeholder="제목 검색"
          prefix={<SearchOutlined />}
          style={{ width: 200 }}
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          onPressEnter={handleSearch}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
          조회
        </Button>
      </Space>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{ pageSize: 50, showTotal: (t) => "총 " + t + "건" }}
        scroll={{ x: 1100 }}
      />

      <Modal
        title="콘텐츠 추가"
        open={createModal}
        onCancel={() => setCreateModal(false)}
        onOk={() => createForm.submit()}
        okText="등록"
        cancelText="취소"
        destroyOnClose
        width={640}
      >
        <PostForm form={createForm} accounts={accounts} onFinish={handleCreate} />
      </Modal>

      <Modal
        title="콘텐츠 수정"
        open={editModal}
        onCancel={() => {
          setEditModal(false);
          setEditing(null);
        }}
        onOk={() => editForm.submit()}
        okText="저장"
        cancelText="취소"
        destroyOnClose
        width={640}
      >
        <PostForm form={editForm} accounts={accounts} onFinish={handleEdit} />
      </Modal>
    </div>
  );
}

interface PostFormProps {
  form: ReturnType<typeof Form.useForm<PostFormValues>>[0];
  accounts: SnsAccount[];
  onFinish: (values: PostFormValues) => void;
}

function PostForm({ form, accounts, onFinish }: PostFormProps) {
  return (
    <Form form={form} layout="vertical" onFinish={onFinish}>
      <Form.Item
        name="account_id"
        label="계정"
        rules={[{ required: true, message: "계정을 선택하세요" }]}
      >
        <Select
          placeholder="계정 선택"
          options={accounts.map((a) => ({ label: buildAccountLabel(a), value: a.id }))}
          showSearch
          optionFilterProp="label"
        />
      </Form.Item>
      <Form.Item
        name="posted_at"
        label="배포일"
        rules={[{ required: true, message: "배포일을 선택하세요" }]}
      >
        <DatePicker style={{ width: "100%" }} />
      </Form.Item>
      <Form.Item name="title" label="제목">
        <Input.TextArea rows={2} placeholder="콘텐츠 제목" />
      </Form.Item>
      <Form.Item name="content_type" label="형태">
        <Select options={CONTENT_TYPE_OPTIONS} placeholder="형태 선택" allowClear />
      </Form.Item>
      <Form.Item name="producer" label="제작">
        <Select options={PRODUCER_OPTIONS} placeholder="제작 선택" allowClear />
      </Form.Item>
      <Space style={{ display: "flex", flexWrap: "wrap" }} size={[16, 0]}>
        <Form.Item name="view_count" label="조회수">
          <InputNumber min={0} style={{ width: 140 }} />
        </Form.Item>
        <Form.Item name="comment_count" label="댓글">
          <InputNumber min={0} style={{ width: 140 }} />
        </Form.Item>
        <Form.Item name="like_count" label="좋아요">
          <InputNumber min={0} style={{ width: 140 }} />
        </Form.Item>
        <Form.Item name="share_count" label="공유">
          <InputNumber min={0} style={{ width: 140 }} />
        </Form.Item>
        <Form.Item name="save_count" label="스크랩">
          <InputNumber min={0} style={{ width: 140 }} />
        </Form.Item>
      </Space>
      <Form.Item name="url" label="URL">
        <Input placeholder="https://..." />
      </Form.Item>
    </Form>
  );
}
