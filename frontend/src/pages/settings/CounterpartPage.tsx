import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
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
  MergeCellsOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import {
  createCounterpart,
  deleteCounterpart,
  listCounterparts,
  mergeCounterparts,
  updateCounterpart,
  type CounterpartCreate,
  type CounterpartListParams,
  type CounterpartRead,
  type CounterpartUpdate,
} from "../../api/counterparts";
import {
  listCategoriesFlat,
  type CategoryRead,
} from "../../api/categories";
import { useAuth } from "../../hooks/useAuth";
import {
  makeErrorExtractor,
  NOT_FOUND_MESSAGE,
  FORBIDDEN_MESSAGE,
} from "../../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;

const extractErrorDetail = makeErrorExtractor({
  statusMessages: {
    404: NOT_FOUND_MESSAGE,
    403: FORBIDDEN_MESSAGE,
  },
  useAxiosMessage: true,
});

interface FormValues {
  name: string;
  aliases?: string[];
  business_registration_no?: string;
  default_category_id?: string;
}

interface MergeValues {
  source_id: string;
  target_id: string;
}

export default function CounterpartPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [items, setItems] = useState<CounterpartRead[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [search, setSearch] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  const [categories, setCategories] = useState<CategoryRead[]>([]);

  // 폼 상태
  const [formOpen, setFormOpen] = useState(false);
  const [formMode, setFormMode] = useState<"create" | "edit">("create");
  const [editing, setEditing] = useState<CounterpartRead | null>(null);
  const [form] = Form.useForm<FormValues>();

  // 통합(merge) 상태
  const [mergeOpen, setMergeOpen] = useState(false);
  const [mergeForm] = Form.useForm<MergeValues>();
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const params: CounterpartListParams = {
        page,
        page_size: pageSize,
        q: search || undefined,
        category_id: categoryFilter,
      };
      const res = await listCounterparts(params);
      setItems(res.items);
      setTotal(res.total);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "거래처 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, search, categoryFilter]);

  useEffect(() => {
    const run = async () => {
      await fetchList();
    };
    void run();
  }, [fetchList]);

  useEffect(() => {
    const run = async () => {
      try {
        const cats = await listCategoriesFlat();
        setCategories(cats);
      } catch {
        // 카테고리 못 불러와도 거래처 페이지는 동작
      }
    };
    void run();
  }, []);

  const categoryOptions = useMemo(
    () =>
      categories.map((c) => ({
        value: c.id,
        label: c.code ? `${c.name} [${c.code}]` : c.name,
      })),
    [categories],
  );

  const openCreate = () => {
    setFormMode("create");
    setEditing(null);
    form.resetFields();
    setFormOpen(true);
  };

  const openEdit = (row: CounterpartRead) => {
    setFormMode("edit");
    setEditing(row);
    form.setFieldsValue({
      name: row.name,
      aliases: row.aliases,
      business_registration_no: row.business_registration_no ?? undefined,
      default_category_id: row.default_category_id ?? undefined,
    });
    setFormOpen(true);
  };

  const handleSubmit = async (values: FormValues) => {
    try {
      if (formMode === "create") {
        const body: CounterpartCreate = {
          name: values.name,
          aliases: values.aliases ?? [],
          business_registration_no: values.business_registration_no ?? null,
          default_category_id: values.default_category_id ?? null,
        };
        await createCounterpart(body);
        message.success("등록되었습니다");
      } else if (editing) {
        const body: CounterpartUpdate = {
          name: values.name,
          aliases: values.aliases ?? [],
          business_registration_no: values.business_registration_no ?? null,
          default_category_id: values.default_category_id ?? null,
        };
        await updateCounterpart(editing.id, body);
        message.success("수정되었습니다");
      }
      setFormOpen(false);
      await fetchList();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "저장 실패"));
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await deleteCounterpart(id);
      message.success("삭제되었습니다");
      await fetchList();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "삭제 실패"));
    }
  };

  const openMerge = () => {
    mergeForm.resetFields();
    if (selectedRowKeys.length === 2) {
      mergeForm.setFieldsValue({
        source_id: selectedRowKeys[0] as string,
        target_id: selectedRowKeys[1] as string,
      });
    }
    setMergeOpen(true);
  };

  const handleMerge = async (values: MergeValues) => {
    if (values.source_id === values.target_id) {
      message.warning("동일한 거래처는 통합할 수 없습니다");
      return;
    }
    try {
      const res = await mergeCounterparts({
        source_id: values.source_id,
        target_id: values.target_id,
      });
      message.success(
        `통합 완료 — ${res.merged_transactions ?? 0}건의 거래가 이전되었습니다`,
      );
      setMergeOpen(false);
      setSelectedRowKeys([]);
      await fetchList();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "통합 실패"));
    }
  };

  const counterpartOptions = useMemo(
    () =>
      items.map((c) => ({
        value: c.id,
        label: `${c.name}${c.business_registration_no ? ` (${c.business_registration_no})` : ""}`,
      })),
    [items],
  );

  const categoryName = (id: string | null | undefined): string => {
    if (!id) return "-";
    return categories.find((c) => c.id === id)?.name ?? "-";
  };

  const columns: ColumnsType<CounterpartRead> = [
    {
      title: "거래처명",
      dataIndex: "name",
      render: (v: string, r) => (
        <Space size={6}>
          <Text strong>{v}</Text>
          {typeof r.transaction_count === "number" && r.transaction_count > 0 && (
            <Tag color="blue" style={{ marginRight: 0 }}>
              {r.transaction_count}건
            </Tag>
          )}
        </Space>
      ),
    },
    {
      title: "별칭",
      dataIndex: "aliases",
      render: (v: string[] | null) => {
        const arr = v ?? [];
        if (arr.length === 0) return "-";
        return (
          <Space size={4} wrap>
            {arr.slice(0, 4).map((a) => (
              <Tag key={a} style={{ marginRight: 0 }}>
                {a}
              </Tag>
            ))}
            {arr.length > 4 && <Text type="secondary">+{arr.length - 4}</Text>}
          </Space>
        );
      },
    },
    {
      title: "사업자번호",
      dataIndex: "business_registration_no",
      width: 140,
      render: (v: string | null) => v || "-",
    },
    {
      title: "기본 카테고리",
      dataIndex: "default_category_id",
      width: 160,
      render: (v: string | null, r) =>
        r.default_category_name ?? categoryName(v),
    },
    {
      title: "",
      width: 120,
      render: (_, record) => (
        <Space size={4}>
          {isAdmin && (
            <>
              <Button
                type="link"
                size="small"
                icon={<EditOutlined />}
                onClick={() => openEdit(record)}
              />
              <Popconfirm
                title="이 거래처를 삭제할까요?"
                okText="삭제"
                cancelText="취소"
                onConfirm={() => handleDelete(record.id)}
              >
                <Button type="link" size="small" danger icon={<DeleteOutlined />} />
              </Popconfirm>
            </>
          )}
        </Space>
      ),
    },
  ];

  return (
    <div style={{ maxWidth: 1480 }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          거래처 관리
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          거래처 마스터 · 별칭·사업자번호·기본 카테고리 매핑 · 중복 거래처 통합
          {!isAdmin && <Text type="warning"> · 보기 전용 (관리자만 편집 가능)</Text>}
        </Paragraph>
      </div>

      <Card
        size="small"
        style={{ marginBottom: 12 }}
        extra={
          <Space>
            {isAdmin && (
              <Button
                icon={<MergeCellsOutlined />}
                onClick={openMerge}
                disabled={selectedRowKeys.length < 2}
              >
                통합 ({selectedRowKeys.length}/2)
              </Button>
            )}
            {isAdmin && (
              <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
                거래처 추가
              </Button>
            )}
          </Space>
        }
      >
        <Space wrap>
          <Input
            placeholder="거래처명/별칭/사업자번호 검색"
            prefix={<SearchOutlined />}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onPressEnter={() => {
              setSearch(searchInput);
              setPage(1);
            }}
            style={{ width: 280 }}
            allowClear
          />
          <Select
            placeholder="카테고리 필터"
            allowClear
            style={{ width: 200 }}
            options={categoryOptions}
            value={categoryFilter}
            onChange={(v) => {
              setCategoryFilter(v);
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
      </Card>

      <Table
        columns={columns}
        dataSource={items}
        rowKey="id"
        loading={loading}
        size="middle"
        rowSelection={
          isAdmin
            ? {
                selectedRowKeys,
                onChange: (keys) => {
                  // 통합용: 최대 2개만 유지
                  if (keys.length > 2) {
                    message.info("통합에는 2개만 선택 가능합니다");
                    setSelectedRowKeys(keys.slice(-2));
                  } else {
                    setSelectedRowKeys(keys);
                  }
                },
              }
            : undefined
        }
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
      />

      <Modal
        title={formMode === "create" ? "거래처 추가" : "거래처 편집"}
        open={formOpen}
        onCancel={() => setFormOpen(false)}
        onOk={() => form.submit()}
        okText="저장"
        cancelText="취소"
        destroyOnClose
        width={520}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit}>
          <Form.Item
            name="name"
            label="거래처명"
            rules={[{ required: true, message: "거래처명을 입력하세요" }]}
          >
            <Input placeholder="예: 한국전력공사" />
          </Form.Item>
          <Form.Item
            name="aliases"
            label="별칭 (Enter 로 추가)"
            tooltip="거래내역에 표기되는 다양한 명칭을 등록하면 자동 매칭에 활용됩니다"
          >
            <Select
              mode="tags"
              placeholder="별칭 입력 후 Enter"
              tokenSeparators={[",", " "]}
              suffixIcon={null}
            />
          </Form.Item>
          <Form.Item name="business_registration_no" label="사업자번호">
            <Input placeholder="000-00-00000" />
          </Form.Item>
          <Form.Item name="default_category_id" label="기본 카테고리">
            <Select
              placeholder="카테고리 선택"
              allowClear
              showSearch
              filterOption={(input, opt) =>
                (opt?.label as string)?.toLowerCase().includes(input.toLowerCase())
              }
              options={categoryOptions}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="거래처 통합"
        open={mergeOpen}
        onCancel={() => setMergeOpen(false)}
        onOk={() => mergeForm.submit()}
        okText="통합 실행"
        cancelText="취소"
        destroyOnClose
        width={520}
      >
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="원본 거래처(source)의 모든 거래내역이 대상 거래처(target)로 이전됩니다."
          description="원본 거래처는 삭제됩니다. 되돌릴 수 없으니 신중히 진행하세요."
        />
        <Form form={mergeForm} layout="vertical" onFinish={handleMerge}>
          <Form.Item
            name="source_id"
            label="원본 거래처 (사라짐)"
            rules={[{ required: true, message: "원본을 선택하세요" }]}
          >
            <Select
              placeholder="원본 거래처"
              showSearch
              filterOption={(input, opt) =>
                (opt?.label as string)?.toLowerCase().includes(input.toLowerCase())
              }
              options={counterpartOptions}
            />
          </Form.Item>
          <Form.Item
            name="target_id"
            label="대상 거래처 (유지됨)"
            rules={[{ required: true, message: "대상을 선택하세요" }]}
          >
            <Select
              placeholder="대상 거래처"
              showSearch
              filterOption={(input, opt) =>
                (opt?.label as string)?.toLowerCase().includes(input.toLowerCase())
              }
              options={counterpartOptions}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
