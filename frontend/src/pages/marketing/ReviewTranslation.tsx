import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import {
  DeleteOutlined,
  EditOutlined,
  SearchOutlined,
  SwapOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import {
  deleteReviewTranslation,
  listReviewTranslations,
  translateAndSave,
  updateReviewTranslation,
  type ReviewTranslation,
} from "../../api/reviewTranslation";
import { extractErrorDetail } from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;
const { TextArea } = Input;

const PLATFORM_OPTIONS = [
  { value: "샤오홍슈", label: "샤오홍슈(小红书)" },
  { value: "웨이보", label: "웨이보(微博)" },
  { value: "더우인", label: "더우인(抖音)" },
  { value: "위챗", label: "위챗(微信)" },
  { value: "기타", label: "기타" },
];

interface InputFormValues {
  campaign?: string;
  reviewer_name?: string;
  platform?: string;
  source_text: string;
}

interface EditFormValues {
  translated_text: string;
  campaign?: string;
  reviewer_name?: string;
  platform?: string;
}

function formatCost(cost: number | null): string {
  if (cost == null) return "-";
  return `$${cost.toFixed(6)}`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function ReviewTranslationPage() {
  const [inputForm] = Form.useForm<InputFormValues>();
  const [editForm] = Form.useForm<EditFormValues>();

  const [translating, setTranslating] = useState(false);
  const [latest, setLatest] = useState<ReviewTranslation | null>(null);

  const [list, setList] = useState<ReviewTranslation[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading, setLoading] = useState(false);

  const [editing, setEditing] = useState<ReviewTranslation | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const res = await listReviewTranslations({
        page,
        page_size: pageSize,
        search: search || undefined,
      });
      setList(res.items);
      setTotal(res.total);
    } catch {
      message.error("번역 목록 조회 실패");
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search]);

  // H-C5: useEffect 안에서 async 함수 직접 호출 금지 — set-state-in-effect 룰 회피.
  useEffect(() => {
    const run = async () => {
      await fetchList();
    };
    void run();
  }, [fetchList]);

  const handleTranslate = async (values: InputFormValues) => {
    setTranslating(true);
    try {
      const created = await translateAndSave({
        source_text: values.source_text,
        campaign: values.campaign || null,
        reviewer_name: values.reviewer_name || null,
        platform: values.platform || null,
      });
      message.success("번역 및 저장 완료");
      setLatest(created);
      inputForm.resetFields(["source_text"]);
      // 목록 첫 페이지로 리프레시
      if (page === 1) {
        await fetchList();
      } else {
        setPage(1);
      }
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "번역 실패"));
    } finally {
      setTranslating(false);
    }
  };

  const openEdit = (record: ReviewTranslation) => {
    setEditing(record);
    editForm.setFieldsValue({
      translated_text: record.translated_text,
      campaign: record.campaign ?? undefined,
      reviewer_name: record.reviewer_name ?? undefined,
      platform: record.platform ?? undefined,
    });
  };

  const handleEdit = async (values: EditFormValues) => {
    if (!editing) return;
    try {
      await updateReviewTranslation(editing.id, {
        translated_text: values.translated_text,
        campaign: values.campaign ?? null,
        reviewer_name: values.reviewer_name ?? null,
        platform: values.platform ?? null,
      });
      message.success("수정 완료");
      setEditing(null);
      editForm.resetFields();
      await fetchList();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "수정 실패"));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteReviewTranslation(id);
      message.success("삭제 완료");
      await fetchList();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "삭제 실패"));
    }
  };

  const columns: ColumnsType<ReviewTranslation> = [
    {
      title: "일시",
      dataIndex: "created_at",
      width: 150,
      render: (v: string) => formatDate(v),
    },
    {
      title: "캠페인",
      dataIndex: "campaign",
      width: 140,
      render: (v: string | null) => v || "-",
    },
    {
      title: "체험단",
      dataIndex: "reviewer_name",
      width: 110,
      render: (v: string | null) => v || "-",
    },
    {
      title: "플랫폼",
      dataIndex: "platform",
      width: 90,
      render: (v: string | null) => (v ? <Tag color="cyan">{v}</Tag> : "-"),
    },
    {
      title: "원문(중국어)",
      dataIndex: "source_text",
      ellipsis: true,
      render: (v: string) => (
        <Text style={{ fontSize: 12 }}>{v.slice(0, 80)}{v.length > 80 ? "…" : ""}</Text>
      ),
    },
    {
      title: "번역문(한국어)",
      dataIndex: "translated_text",
      ellipsis: true,
      render: (v: string) => (
        <Text style={{ fontSize: 12 }}>{v.slice(0, 80)}{v.length > 80 ? "…" : ""}</Text>
      ),
    },
    {
      title: "비용",
      dataIndex: "cost_usd",
      width: 100,
      align: "right" as const,
      render: (v: number | null) => formatCost(v),
    },
    {
      title: "",
      width: 90,
      render: (_, record) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openEdit(record)}
          />
          <Popconfirm
            title="삭제하시겠습니까?"
            okText="삭제"
            cancelText="취소"
            onConfirm={() => handleDelete(record.id)}
          >
            <Button type="link" size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 1280 }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          체험단 번역
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          중국 체험단(샤오홍슈/웨이보 등) 후기를 자동 한국어 번역해 저장합니다 · 모델 Haiku 4.5
        </Paragraph>
      </div>

      <div style={{ display: "grid", gap: 16, gridTemplateColumns: "1fr 1fr", marginBottom: 28 }}>
        <Card title="원문 입력" size="small">
          <Form
            form={inputForm}
            layout="vertical"
            onFinish={handleTranslate}
            initialValues={{ platform: undefined }}
          >
            <Space style={{ width: "100%" }} size={8} wrap>
              <Form.Item name="campaign" label="캠페인명" style={{ marginBottom: 12, width: 200 }}>
                <Input placeholder="예: 2026 봄 신상 체험단" />
              </Form.Item>
              <Form.Item name="reviewer_name" label="체험단명" style={{ marginBottom: 12, width: 160 }}>
                <Input placeholder="체험단 닉네임" />
              </Form.Item>
              <Form.Item name="platform" label="플랫폼" style={{ marginBottom: 12, width: 160 }}>
                <Select
                  placeholder="플랫폼 선택"
                  allowClear
                  options={PLATFORM_OPTIONS}
                />
              </Form.Item>
            </Space>
            <Form.Item
              name="source_text"
              label="중국어 원문"
              rules={[{ required: true, message: "원문을 입력하세요" }]}
            >
              <TextArea
                rows={10}
                placeholder="여기에 중국어 후기를 붙여넣으세요…"
                showCount
                maxLength={20000}
              />
            </Form.Item>
            <Button
              type="primary"
              icon={<SwapOutlined />}
              loading={translating}
              onClick={() => inputForm.submit()}
              block
            >
              번역하고 저장하기
            </Button>
          </Form>
        </Card>

        <Card title="번역 결과 (방금 번역됨)" size="small">
          {latest ? (
            <div>
              <Space size={6} wrap style={{ marginBottom: 12 }}>
                {latest.platform && <Tag color="cyan">{latest.platform}</Tag>}
                {latest.campaign && <Tag>{latest.campaign}</Tag>}
                {latest.reviewer_name && <Tag color="geekblue">{latest.reviewer_name}</Tag>}
                <Tag color="purple">{latest.model_used}</Tag>
                <Tag>{formatCost(latest.cost_usd)}</Tag>
              </Space>
              <Paragraph
                style={{
                  whiteSpace: "pre-wrap",
                  background: "#fafafa",
                  padding: 12,
                  borderRadius: 6,
                  minHeight: 200,
                  margin: 0,
                  fontSize: 13,
                  lineHeight: 1.7,
                }}
              >
                {latest.translated_text}
              </Paragraph>
              <Button
                type="link"
                style={{ padding: 0, marginTop: 8 }}
                onClick={() => openEdit(latest)}
              >
                번역문 직접 편집하기
              </Button>
            </div>
          ) : (
            <Empty description="원문을 입력하고 [번역하고 저장하기]를 누르면 결과가 표시됩니다" />
          )}
        </Card>
      </div>

      <Card
        title="저장된 번역 기록"
        size="small"
        extra={
          <Space>
            <Input
              placeholder="원문/번역문/체험단명 검색"
              prefix={<SearchOutlined />}
              style={{ width: 260 }}
              allowClear
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onPressEnter={() => {
                setSearch(searchInput);
                setPage(1);
              }}
            />
            <Button
              onClick={() => {
                setSearch(searchInput);
                setPage(1);
              }}
            >
              조회
            </Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={list}
          rowKey="id"
          loading={loading}
          size="middle"
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: true,
            pageSizeOptions: [10, 20, 50, 100],
            showTotal: (t) => `총 ${t}건`,
            onChange: (p, ps) => {
              setPage(p);
              setPageSize(ps);
            },
          }}
          expandable={{
            expandedRowRender: (record) => (
              <div style={{ display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr" }}>
                <div>
                  <Text strong>원문(중국어)</Text>
                  <Paragraph
                    style={{
                      whiteSpace: "pre-wrap",
                      background: "#fafafa",
                      padding: 8,
                      borderRadius: 4,
                      marginTop: 6,
                      fontSize: 12,
                    }}
                  >
                    {record.source_text}
                  </Paragraph>
                </div>
                <div>
                  <Text strong>번역문(한국어)</Text>
                  <Paragraph
                    style={{
                      whiteSpace: "pre-wrap",
                      background: "#f0f8ff",
                      padding: 8,
                      borderRadius: 4,
                      marginTop: 6,
                      fontSize: 12,
                    }}
                  >
                    {record.translated_text}
                  </Paragraph>
                </div>
              </div>
            ),
          }}
        />
      </Card>

      <Modal
        title="번역 편집"
        open={editing !== null}
        onCancel={() => {
          setEditing(null);
          editForm.resetFields();
        }}
        onOk={() => editForm.submit()}
        okText="저장"
        cancelText="취소"
        destroyOnClose
        width={720}
      >
        <Form form={editForm} layout="vertical" onFinish={handleEdit}>
          <Space style={{ width: "100%" }} size={8} wrap>
            <Form.Item name="campaign" label="캠페인명" style={{ marginBottom: 12, width: 220 }}>
              <Input placeholder="캠페인명" />
            </Form.Item>
            <Form.Item name="reviewer_name" label="체험단명" style={{ marginBottom: 12, width: 180 }}>
              <Input placeholder="체험단 닉네임" />
            </Form.Item>
            <Form.Item name="platform" label="플랫폼" style={{ marginBottom: 12, width: 180 }}>
              <Select placeholder="플랫폼" allowClear options={PLATFORM_OPTIONS} />
            </Form.Item>
          </Space>
          <Form.Item
            name="translated_text"
            label="번역문(한국어)"
            rules={[{ required: true, message: "번역문을 입력하세요" }]}
          >
            <TextArea rows={10} showCount maxLength={20000} />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
