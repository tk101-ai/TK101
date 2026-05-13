import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Button,
  Empty,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  message,
} from "antd";
import {
  EditOutlined,
  PlusOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import {
  ACCOUNT_TYPE_LABEL,
  ACCOUNT_TYPE_OPTIONS,
  ACCOUNT_TYPE_TAG_COLOR,
  CURRENCY_OPTIONS,
  createAccount,
  listAccounts,
  updateAccount,
  type Account,
  type AccountCreate,
  type AccountType,
  type AccountUpdate,
  type Currency,
} from "../api/accounts";
import { useAuth } from "../hooks/useAuth";
import { extractErrorDetail } from "../utils/errorUtils";

const { Title, Paragraph, Text } = Typography;

const BANK_OPTIONS = [
  { value: "KB국민은행", label: "KB국민은행" },
  { value: "IBK기업은행", label: "IBK기업은행" },
  { value: "NH농협은행", label: "NH농협은행" },
  { value: "신한은행", label: "신한은행" },
  { value: "우리은행", label: "우리은행" },
  { value: "하나은행", label: "하나은행" },
  { value: "SC제일은행", label: "SC제일은행" },
  { value: "씨티은행", label: "씨티은행" },
  { value: "KEB하나은행", label: "KEB하나은행" },
  { value: "카카오뱅크", label: "카카오뱅크" },
  { value: "토스뱅크", label: "토스뱅크" },
  { value: "기타", label: "기타" },
];

const TYPE_FILTER_OPTIONS = [
  { value: "all", label: "전체 유형" },
  ...ACCOUNT_TYPE_OPTIONS.map((o) => ({ value: o.value, label: o.label })),
];

const CURRENCY_FILTER_OPTIONS = [
  { value: "all", label: "전체 통화" },
  ...CURRENCY_OPTIONS.map((o) => ({ value: o.value, label: o.value })),
];

function formatBalance(balance: string | null, currency: Currency): string {
  if (balance == null || balance === "") return "—";
  const n = Number(balance);
  if (!Number.isFinite(n)) return balance;
  const formatted = n.toLocaleString("ko-KR", {
    minimumFractionDigits: currency === "KRW" ? 0 : 2,
    maximumFractionDigits: currency === "KRW" ? 0 : 2,
  });
  return `${currency} ${formatted}`;
}

function formatSyncedAt(iso: string | null): string {
  if (!iso) return "—";
  return dayjs(iso).format("YYYY-MM-DD");
}

interface CreateFormValues {
  bank_name: string;
  account_number: string;
  account_holder: string;
  account_type?: AccountType;
  currency: Currency;
  account_label?: string;
  alias?: string;
  business_registration_no?: string;
}

interface EditFormValues {
  account_holder: string;
  account_type?: AccountType;
  account_label?: string;
  alias?: string;
  business_registration_no?: string;
  is_active: boolean;
}

export default function Accounts() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [data, setData] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);

  const [createModal, setCreateModal] = useState(false);
  const [createForm] = Form.useForm<CreateFormValues>();

  const [editing, setEditing] = useState<Account | null>(null);
  const [editForm] = Form.useForm<EditFormValues>();

  const [searchInput, setSearchInput] = useState("");
  const [typeFilter, setTypeFilter] = useState<string>("all");
  const [currencyFilter, setCurrencyFilter] = useState<string>("all");
  const [showInactive, setShowInactive] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const items = await listAccounts();
      setData(items);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "계좌 목록 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, []);

  // useEffect 안에서 async 직접 호출 회피
  useEffect(() => {
    const run = async () => {
      await fetchData();
    };
    void run();
  }, [fetchData]);

  // 클라이언트 사이드 필터링
  const filtered = useMemo(() => {
    const q = searchInput.trim().toLowerCase();
    return data.filter((a) => {
      if (!showInactive && !a.is_active) return false;
      if (typeFilter !== "all" && a.account_type !== typeFilter) return false;
      if (currencyFilter !== "all" && a.currency !== currencyFilter) return false;
      if (q) {
        const haystack = [
          a.bank_name,
          a.account_number,
          a.account_holder,
          a.alias ?? "",
          a.account_label ?? "",
        ]
          .join(" ")
          .toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }, [data, searchInput, typeFilter, currencyFilter, showInactive]);

  const handleCreate = async (values: CreateFormValues) => {
    try {
      const payload: AccountCreate = {
        bank_name: values.bank_name,
        account_number: values.account_number,
        account_holder: values.account_holder,
        account_type: values.account_type ?? null,
        currency: values.currency,
        account_label: values.account_label?.trim() || null,
        alias: values.alias?.trim() || null,
        business_registration_no:
          values.business_registration_no?.trim() || null,
      };
      await createAccount(payload);
      message.success("계좌 등록 완료");
      setCreateModal(false);
      createForm.resetFields();
      await fetchData();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "계좌 등록 실패"));
    }
  };

  const openEdit = (record: Account) => {
    setEditing(record);
    editForm.setFieldsValue({
      account_holder: record.account_holder,
      account_type: record.account_type ?? undefined,
      account_label: record.account_label ?? undefined,
      alias: record.alias ?? undefined,
      business_registration_no: record.business_registration_no ?? undefined,
      is_active: record.is_active,
    });
  };

  const handleEdit = async (values: EditFormValues) => {
    if (!editing) return;
    try {
      const payload: AccountUpdate = {
        account_holder: values.account_holder,
        account_type: values.account_type ?? null,
        account_label: values.account_label?.trim() || null,
        alias: values.alias?.trim() || null,
        business_registration_no:
          values.business_registration_no?.trim() || null,
        is_active: values.is_active,
      };
      await updateAccount(editing.id, payload);
      message.success("계좌 정보가 수정되었습니다");
      setEditing(null);
      editForm.resetFields();
      await fetchData();
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "계좌 수정 실패"));
    }
  };

  const handleToggleActive = async (record: Account) => {
    const nextActive = !record.is_active;
    try {
      await updateAccount(record.id, { is_active: nextActive });
      message.success(
        nextActive
          ? "계좌가 활성화되었습니다"
          : "계좌가 비활성화되었습니다",
      );
      await fetchData();
    } catch (err: unknown) {
      message.error(
        extractErrorDetail(
          err,
          nextActive ? "활성화 실패" : "비활성화 실패",
        ),
      );
    }
  };

  const columns: ColumnsType<Account> = [
    {
      title: "은행",
      dataIndex: "bank_name",
      width: 120,
    },
    {
      title: "계좌번호",
      dataIndex: "account_number",
      width: 200,
      render: (v: string, record: Account) => (
        <div>
          <div style={{ fontFamily: "monospace", fontSize: 13 }}>{v}</div>
          {record.alias && (
            <Text type="secondary" style={{ fontSize: 11 }}>
              별칭: {record.alias}
            </Text>
          )}
        </div>
      ),
    },
    {
      title: "예금주",
      dataIndex: "account_holder",
      width: 130,
    },
    {
      title: "유형",
      dataIndex: "account_type",
      width: 100,
      render: (v: AccountType | null, record: Account) => {
        if (!v) return <Tag>—</Tag>;
        const label = ACCOUNT_TYPE_LABEL[v];
        const color = ACCOUNT_TYPE_TAG_COLOR[v];
        return (
          <Space size={4} direction="vertical">
            <Tag color={color}>{label}</Tag>
            {record.account_label && (
              <Text type="secondary" style={{ fontSize: 11 }}>
                {record.account_label}
              </Text>
            )}
          </Space>
        );
      },
    },
    {
      title: "통화",
      dataIndex: "currency",
      width: 80,
      render: (v: Currency) => <Tag>{v}</Tag>,
    },
    {
      title: "현재 잔액",
      dataIndex: "current_balance",
      width: 160,
      align: "right" as const,
      render: (v: string | null, record: Account) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>
          {formatBalance(v, record.currency)}
        </span>
      ),
    },
    {
      title: "마지막 거래",
      dataIndex: "last_synced_at",
      width: 110,
      render: (v: string | null) => (
        <Text type={v ? undefined : "secondary"} style={{ fontSize: 12 }}>
          {formatSyncedAt(v)}
        </Text>
      ),
    },
    {
      title: "사업자번호",
      dataIndex: "business_registration_no",
      width: 130,
      render: (v: string | null) => v || "—",
    },
    {
      title: "상태",
      dataIndex: "is_active",
      width: 100,
      render: (v: boolean, record: Account) =>
        isAdmin ? (
          <Popconfirm
            title={v ? "이 계좌를 비활성화할까요?" : "이 계좌를 활성화할까요?"}
            okText={v ? "비활성화" : "활성화"}
            cancelText="취소"
            onConfirm={() => handleToggleActive(record)}
          >
            <Switch
              checked={v}
              checkedChildren="활성"
              unCheckedChildren="비활성"
            />
          </Popconfirm>
        ) : (
          <Tag color={v ? "green" : "default"}>{v ? "활성" : "비활성"}</Tag>
        ),
    },
    {
      title: "",
      width: 60,
      render: (_, record) =>
        isAdmin ? (
          <Tooltip title="편집">
            <Button
              type="link"
              size="small"
              icon={<EditOutlined />}
              onClick={() => openEdit(record)}
            />
          </Tooltip>
        ) : null,
    },
  ];

  const emptyState = (
    <Empty
      description={
        <div>
          <div>등록된 계좌가 없습니다.</div>
          <Text type="secondary" style={{ fontSize: 12 }}>
            관리자 계정으로 [계좌 등록] 버튼을 누르거나, 추후 엑셀 업로드로
            자동 등록할 수 있습니다.
          </Text>
        </div>
      }
    >
      {isAdmin && (
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => setCreateModal(true)}
        >
          계좌 등록
        </Button>
      )}
    </Empty>
  );

  return (
    <div style={{ maxWidth: 1480 }}>
      <div style={{ marginBottom: 24 }}>
        <Title level={3} style={{ margin: 0, letterSpacing: "-0.02em" }}>
          계좌 관리
        </Title>
        <Paragraph type="secondary" style={{ margin: "4px 0 0" }}>
          회사 명의의 은행 계좌를 등록·관리합니다. 일반/외화/대출/기보보증 유형과
          통화별 잔액을 관리할 수 있습니다.
        </Paragraph>
      </div>

      <div
        style={{
          display: "flex",
          gap: 12,
          flexWrap: "wrap",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 16,
        }}
      >
        <Space size={8} wrap>
          <Input
            placeholder="은행·계좌번호·예금주·별칭 검색"
            prefix={<SearchOutlined />}
            allowClear
            style={{ width: 260 }}
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
          <Select
            value={typeFilter}
            onChange={setTypeFilter}
            options={TYPE_FILTER_OPTIONS}
            style={{ width: 140 }}
          />
          <Select
            value={currencyFilter}
            onChange={setCurrencyFilter}
            options={CURRENCY_FILTER_OPTIONS}
            style={{ width: 140 }}
          />
          <Space size={6}>
            <Switch
              checked={showInactive}
              onChange={setShowInactive}
              size="small"
            />
            <Text style={{ fontSize: 13 }}>비활성 포함</Text>
          </Space>
        </Space>

        {isAdmin && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => setCreateModal(true)}
          >
            계좌 등록
          </Button>
        )}
      </div>

      <Table
        columns={columns}
        dataSource={filtered}
        rowKey="id"
        loading={loading}
        size="middle"
        scroll={{ x: 1280 }}
        locale={{ emptyText: emptyState }}
        pagination={{
          pageSize: 20,
          showSizeChanger: true,
          pageSizeOptions: [10, 20, 50, 100],
          showTotal: (t) => `총 ${t}건`,
        }}
      />

      {/* 등록 모달 */}
      <Modal
        title="계좌 등록"
        open={createModal}
        onCancel={() => {
          setCreateModal(false);
          createForm.resetFields();
        }}
        onOk={() => createForm.submit()}
        okText="등록"
        cancelText="취소"
        destroyOnClose
        width={640}
      >
        <Form
          form={createForm}
          onFinish={handleCreate}
          layout="vertical"
          initialValues={{ currency: "KRW", account_type: "general" }}
        >
          <div
            style={{
              display: "grid",
              gap: 12,
              gridTemplateColumns: "1fr 1fr",
            }}
          >
            <Form.Item
              name="bank_name"
              label="은행명"
              rules={[{ required: true, message: "은행을 선택하세요" }]}
            >
              <Select
                showSearch
                placeholder="은행 선택"
                options={BANK_OPTIONS}
                optionFilterProp="label"
              />
            </Form.Item>
            <Form.Item
              name="account_number"
              label="계좌번호"
              rules={[{ required: true, message: "계좌번호를 입력하세요" }]}
            >
              <Input placeholder="000-000000-00-000" />
            </Form.Item>
            <Form.Item
              name="account_holder"
              label="예금주"
              rules={[{ required: true, message: "예금주를 입력하세요" }]}
            >
              <Input placeholder="예금주명" />
            </Form.Item>
            <Form.Item
              name="account_type"
              label="계좌 유형"
              rules={[{ required: true, message: "유형을 선택하세요" }]}
            >
              <Select options={ACCOUNT_TYPE_OPTIONS} placeholder="유형 선택" />
            </Form.Item>
            <Form.Item
              name="currency"
              label="통화"
              rules={[{ required: true, message: "통화를 선택하세요" }]}
            >
              <Select options={CURRENCY_OPTIONS} placeholder="통화 선택" />
            </Form.Item>
            <Form.Item name="account_label" label="계좌 라벨 (선택)">
              <Input placeholder='예: "외화", "대출"' maxLength={50} />
            </Form.Item>
            <Form.Item name="alias" label="별칭 (선택)">
              <Input placeholder="예: 마케팅 운영 계좌" maxLength={50} />
            </Form.Item>
            <Form.Item
              name="business_registration_no"
              label="사업자등록번호 (선택)"
            >
              <Input placeholder="000-00-00000" />
            </Form.Item>
          </div>
        </Form>
      </Modal>

      {/* 편집 모달 */}
      <Modal
        title="계좌 편집"
        open={editing !== null}
        onCancel={() => {
          setEditing(null);
          editForm.resetFields();
        }}
        onOk={() => editForm.submit()}
        okText="저장"
        cancelText="취소"
        destroyOnClose
        width={640}
      >
        {editing && (
          <>
            <Paragraph type="secondary" style={{ marginTop: 0 }}>
              <Text strong>{editing.bank_name}</Text> · {editing.account_number}{" "}
              · <Tag>{editing.currency}</Tag>
              <br />
              <Text type="secondary" style={{ fontSize: 12 }}>
                ※ 거래 무결성을 위해 은행·계좌번호·통화는 변경할 수 없습니다.
              </Text>
            </Paragraph>
            <Form form={editForm} onFinish={handleEdit} layout="vertical">
              <div
                style={{
                  display: "grid",
                  gap: 12,
                  gridTemplateColumns: "1fr 1fr",
                }}
              >
                <Form.Item
                  name="account_holder"
                  label="예금주"
                  rules={[
                    { required: true, message: "예금주를 입력하세요" },
                  ]}
                >
                  <Input placeholder="예금주명" />
                </Form.Item>
                <Form.Item name="account_type" label="계좌 유형">
                  <Select
                    options={ACCOUNT_TYPE_OPTIONS}
                    placeholder="유형 선택"
                    allowClear
                  />
                </Form.Item>
                <Form.Item name="account_label" label="계좌 라벨 (선택)">
                  <Input placeholder='예: "외화", "대출"' maxLength={50} />
                </Form.Item>
                <Form.Item name="alias" label="별칭 (선택)">
                  <Input placeholder="사용자 친화 별칭" maxLength={50} />
                </Form.Item>
                <Form.Item
                  name="business_registration_no"
                  label="사업자등록번호 (선택)"
                >
                  <Input placeholder="000-00-00000" />
                </Form.Item>
                <Form.Item
                  name="is_active"
                  label="활성 상태"
                  valuePropName="checked"
                >
                  <Switch checkedChildren="활성" unCheckedChildren="비활성" />
                </Form.Item>
              </div>
            </Form>
          </>
        )}
      </Modal>
    </div>
  );
}
