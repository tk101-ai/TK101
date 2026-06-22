import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AutoComplete,
  Button,
  DatePicker,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Popover,
  Select,
  Space,
  Switch,
  Table,
  Tag,
  Tooltip,
  Typography,
  Upload,
  message,
} from "antd";
import {
  DeleteOutlined,
  DownloadOutlined,
  LinkOutlined,
  PaperClipOutlined,
  PlusOutlined,
  ReloadOutlined,
  SearchOutlined,
  SyncOutlined,
  UndoOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type { TableRowSelection } from "antd/es/table/interface";
import dayjs, { Dayjs } from "dayjs";
import {
  createTransaction,
  deleteTransaction,
  downloadExcel,
  getCounterparts,
  listTransactions,
  removeMatch,
  restoreTransaction,
  runMatching,
  updateTransaction,
  uploadTransactions,
  type CounterpartSuggestion,
  type MatchStatus,
  type Transaction,
  type TransactionCreate,
  type TransactionFilter,
  type TransactionType,
  type TransactionUpdate,
} from "../api/transactions";
import { listCategoriesFlat, type CategoryRead } from "../api/categories";
import { listAccounts, type Account } from "../api/accounts";
import { useAuth } from "../hooks/useAuth";
import { extractErrorDetail } from "../utils/errorUtils";
import { triggerBlobDownload } from "../utils/download";
import TransactionFormModal from "../components/finance/TransactionFormModal";
import AttachmentModal from "../components/finance/AttachmentModal";
import MatchingCandidatesModal from "../components/finance/MatchingCandidatesModal";

const { RangePicker } = DatePicker;

// ---------------------------------------------------------------------------
// 헬퍼
// ---------------------------------------------------------------------------

function formatAmount(v: string | null | undefined): string {
  if (v == null || v === "") return "-";
  return `${Number(v).toLocaleString("ko-KR")}원`;
}

interface RoleBased {
  isAdmin: boolean;
}

// ---------------------------------------------------------------------------
// 인라인 카테고리 셀
// ---------------------------------------------------------------------------

interface CategoryCellProps {
  value: string | null | undefined;
  categories: CategoryRead[];
  onChange: (categoryId: string | null) => Promise<void> | void;
}

function CategoryCell({ value, categories, onChange }: CategoryCellProps) {
  const [saving, setSaving] = useState(false);
  const options = useMemo(
    () => categories.map((c) => ({ label: c.name, value: c.id })),
    [categories],
  );
  return (
    <Select
      size="small"
      value={value ?? undefined}
      onChange={async (v) => {
        setSaving(true);
        try {
          await onChange(v ?? null);
        } finally {
          setSaving(false);
        }
      }}
      onClear={async () => {
        setSaving(true);
        try {
          await onChange(null);
        } finally {
          setSaving(false);
        }
      }}
      options={options}
      placeholder="선택"
      allowClear
      showSearch
      optionFilterProp="label"
      style={{ width: "100%" }}
      loading={saving}
    />
  );
}

// ---------------------------------------------------------------------------
// 인라인 메모 셀 (Popover 편집)
// ---------------------------------------------------------------------------

interface MemoCellProps {
  value: string | null;
  onSave: (memo: string | null) => Promise<void> | void;
}

function MemoCell({ value, onSave }: MemoCellProps) {
  // H-2 정리: 부모에서 `key={value ?? "__empty__"}` 로 재마운트시키므로
  // value prop 동기화용 useEffect 제거 (set-state-in-effect 회피).
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(draft.trim() === "" ? null : draft);
      setOpen(false);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Popover
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (v) setDraft(value ?? "");
      }}
      trigger="click"
      placement="topLeft"
      destroyTooltipOnHide
      content={
        <div style={{ width: 260 }}>
          <Input.TextArea
            autoFocus
            rows={3}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="메모를 입력하세요"
          />
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 8 }}>
            <Button size="small" onClick={() => setOpen(false)}>취소</Button>
            <Button size="small" type="primary" loading={saving} onClick={handleSave}>
              저장
            </Button>
          </div>
        </div>
      }
    >
      <Button type="link" size="small" style={{ padding: 0 }}>
        {value && value.length > 0 ? (
          <span title={value}>
            {value.length > 10 ? value.slice(0, 10) + "…" : value}
          </span>
        ) : (
          <Typography.Text type="secondary">메모 추가</Typography.Text>
        )}
      </Button>
    </Popover>
  );
}

// ---------------------------------------------------------------------------
// 일괄 카테고리 / 일괄 메모 모달
// ---------------------------------------------------------------------------

interface BulkCategoryModalProps {
  open: boolean;
  count: number;
  categories: CategoryRead[];
  onCancel: () => void;
  onConfirm: (categoryId: string | null) => Promise<void>;
}

function BulkCategoryModal({
  open,
  count,
  categories,
  onCancel,
  onConfirm,
}: BulkCategoryModalProps) {
  // H-2 정리: 부모에서 `key={open ? "open" : "closed"}` 로 재마운트되어
  // 항상 초기값 undefined 로 시작하므로 useEffect 동기화 불필요.
  const [value, setValue] = useState<string | undefined>();
  const [loading, setLoading] = useState(false);

  return (
    <Modal
      title={`선택 거래 ${count}건 카테고리 일괄 변경`}
      open={open}
      onCancel={onCancel}
      okText="적용"
      cancelText="취소"
      confirmLoading={loading}
      onOk={async () => {
        setLoading(true);
        try {
          await onConfirm(value ?? null);
        } finally {
          setLoading(false);
        }
      }}
      destroyOnClose
    >
      <Form layout="vertical">
        <Form.Item label="카테고리">
          <Select
            value={value}
            onChange={setValue}
            options={categories.map((c) => ({ label: c.name, value: c.id }))}
            placeholder="카테고리 선택 (비우면 해제)"
            allowClear
            showSearch
            optionFilterProp="label"
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}

interface BulkMemoModalProps {
  open: boolean;
  count: number;
  onCancel: () => void;
  onConfirm: (memo: string | null) => Promise<void>;
}

function BulkMemoModal({ open, count, onCancel, onConfirm }: BulkMemoModalProps) {
  // H-2 정리: 부모에서 `key` 로 재마운트되어 항상 빈 문자열로 시작.
  const [value, setValue] = useState("");
  const [loading, setLoading] = useState(false);

  return (
    <Modal
      title={`선택 거래 ${count}건 메모 일괄 입력`}
      open={open}
      onCancel={onCancel}
      okText="적용"
      cancelText="취소"
      confirmLoading={loading}
      onOk={async () => {
        setLoading(true);
        try {
          await onConfirm(value.trim() === "" ? null : value);
        } finally {
          setLoading(false);
        }
      }}
      destroyOnClose
    >
      <Input.TextArea
        rows={4}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="메모 (비우면 메모 삭제)"
      />
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// 메인 페이지
// ---------------------------------------------------------------------------

const DEFAULT_PAGE_SIZE = 50;

export default function Transactions() {
  const { user } = useAuth();
  const role: RoleBased = { isAdmin: user?.role === "admin" };

  const [data, setData] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<CategoryRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);

  // 페이지네이션 (서버 페이징)
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  // 필터 (debounce 적용)
  const [filters, setFilters] = useState<Omit<TransactionFilter, "limit" | "offset">>({});

  // 모달/UI 상태
  const [uploadModal, setUploadModal] = useState(false);
  const [uploadAccountId, setUploadAccountId] = useState<string>("");
  const [createModal, setCreateModal] = useState(false);
  const [creating, setCreating] = useState(false);
  const [attachmentTarget, setAttachmentTarget] = useState<string | null>(null);
  const [matchTarget, setMatchTarget] = useState<Transaction | null>(null);
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [bulkCategoryOpen, setBulkCategoryOpen] = useState(false);
  const [bulkMemoOpen, setBulkMemoOpen] = useState(false);

  // 거래처 자동완성
  const [counterpartOptions, setCounterpartOptions] = useState<CounterpartSuggestion[]>([]);
  const [counterpartQuery, setCounterpartQuery] = useState<string>("");

  const accountMap = useMemo(
    () => new Map(accounts.map((a) => [a.id, a])),
    [accounts],
  );
  const categoryMap = useMemo(
    () => new Map(categories.map((c) => [c.id, c])),
    [categories],
  );

  // -------------------------------------------------------------------------
  // 데이터 로드
  // -------------------------------------------------------------------------

  const fetchTransactions = useCallback(
    async (
      currentPage: number,
      currentSize: number,
      currentFilters: Omit<TransactionFilter, "limit" | "offset">,
    ) => {
      setLoading(true);
      try {
        const offset = (currentPage - 1) * currentSize;
        const result = await listTransactions({
          ...currentFilters,
          limit: currentSize,
          offset,
        });
        setData(result.items);
        setTotal(result.total);
      } catch (err) {
        message.error(extractErrorDetail(err, "거래내역을 불러오지 못했습니다"));
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  // 마운트 시 한 번: 계좌 + 카테고리
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      try {
        const [accts, cats] = await Promise.all([
          listAccounts(),
          listCategoriesFlat().catch(() => [] as CategoryRead[]),
        ]);
        if (cancelled) return;
        setAccounts(accts);
        setCategories(cats);
      } catch {
        // 계좌 로드 실패는 거래 페이지 자체를 막지 않는다.
      }
    };
    void run();
    return () => {
      cancelled = true;
    };
  }, []);

  // 필터/페이지 변경 시 debounce + 자동 재조회.
  // H-1 정리: filtersRef 를 제거하고 deps 에 filters 를 직접 포함.
  // setTimeout closure 가 stale 한 filters 를 잡더라도, cleanup 으로 새 effect 가
  // 재실행되며 항상 최신 값으로 호출된다.
  useEffect(() => {
    const handle = window.setTimeout(() => {
      void fetchTransactions(page, pageSize, filters);
    }, 300);
    return () => window.clearTimeout(handle);
  }, [filters, page, pageSize, fetchTransactions]);

  // 거래처 자동완성 debounce
  useEffect(() => {
    const handle = window.setTimeout(() => {
      const run = async () => {
        try {
          const result = await getCounterparts(counterpartQuery, 10);
          setCounterpartOptions(result);
        } catch {
          // 자동완성 실패는 조용히 무시
        }
      };
      void run();
    }, 250);
    return () => window.clearTimeout(handle);
  }, [counterpartQuery]);

  // -------------------------------------------------------------------------
  // 필터 setter 헬퍼
  // -------------------------------------------------------------------------

  const updateFilter = <K extends keyof typeof filters>(
    key: K,
    value: (typeof filters)[K] | undefined,
  ) => {
    setPage(1);
    setFilters((prev) => {
      const next = { ...prev };
      if (value === undefined || value === null || value === "") {
        delete next[key];
      } else {
        next[key] = value;
      }
      return next;
    });
  };

  const resetFilters = () => {
    setPage(1);
    setFilters({});
    setCounterpartQuery("");
  };

  // -------------------------------------------------------------------------
  // 액션 핸들러
  // -------------------------------------------------------------------------

  const handleDownload = async () => {
    try {
      const res = await downloadExcel(filters);
      triggerBlobDownload(
        new Blob([res.data]),
        "거래내역_" + dayjs().format("YYYYMMDD") + ".xlsx",
      );
    } catch (err) {
      message.error(extractErrorDetail(err, "다운로드 실패"));
    }
  };

  const handleAutoMatch = async () => {
    try {
      const res = await runMatching();
      message.success((res.data.matched_count ?? 0) + "건 매칭 완료");
      fetchTransactions(page, pageSize, filters);
    } catch (err) {
      message.error(extractErrorDetail(err, "매칭 실패"));
    }
  };

  const handleExcelUpload = async (file: File): Promise<boolean> => {
    if (!uploadAccountId) {
      message.error("계좌를 선택해주세요");
      return false;
    }
    try {
      const res = await uploadTransactions(uploadAccountId, file);
      message.success((res.data?.row_count ?? 0) + "건 업로드 완료");
      setUploadModal(false);
      fetchTransactions(page, pageSize, filters);
    } catch (err) {
      message.error(extractErrorDetail(err, "업로드 실패"));
    }
    return false;
  };

  const handleCreate = async (body: TransactionCreate) => {
    setCreating(true);
    try {
      await createTransaction(body);
      message.success("거래 등록 완료");
      setCreateModal(false);
      fetchTransactions(page, pageSize, filters);
    } catch (err) {
      message.error(extractErrorDetail(err, "거래 등록 실패"));
    } finally {
      setCreating(false);
    }
  };

  const patchTransaction = useCallback(
    async (id: string, body: TransactionUpdate, successMsg?: string) => {
      try {
        const updated = await updateTransaction(id, body);
        setData((prev) => prev.map((t) => (t.id === id ? updated : t)));
        if (successMsg) message.success(successMsg);
      } catch (err) {
        message.error(extractErrorDetail(err, "수정 실패"));
      }
    },
    [],
  );

  const handleDelete = async (id: string) => {
    try {
      await deleteTransaction(id);
      message.success("거래 삭제 (비활성화)");
      fetchTransactions(page, pageSize, filters);
    } catch (err) {
      message.error(extractErrorDetail(err, "삭제 실패"));
    }
  };

  const handleRestore = async (id: string) => {
    try {
      await restoreTransaction(id);
      message.success("복원 완료");
      fetchTransactions(page, pageSize, filters);
    } catch (err) {
      message.error(extractErrorDetail(err, "복원 실패"));
    }
  };

  const handleRemoveMatch = async (id: string) => {
    try {
      await removeMatch(id);
      message.success("매칭 해제");
      fetchTransactions(page, pageSize, filters);
    } catch (err) {
      message.error(extractErrorDetail(err, "매칭 해제 실패"));
    }
  };

  const handleBulkCategory = async (categoryId: string | null) => {
    const ids = selectedRowKeys.map(String);
    try {
      await Promise.all(
        ids.map((id) =>
          updateTransaction(id, { category_id: categoryId }),
        ),
      );
      message.success(`${ids.length}건 카테고리 변경 완료`);
      setBulkCategoryOpen(false);
      setSelectedRowKeys([]);
      fetchTransactions(page, pageSize, filters);
    } catch (err) {
      message.error(extractErrorDetail(err, "일괄 카테고리 변경 실패"));
    }
  };

  const handleBulkMemo = async (memo: string | null) => {
    const ids = selectedRowKeys.map(String);
    try {
      await Promise.all(ids.map((id) => updateTransaction(id, { memo })));
      message.success(`${ids.length}건 메모 변경 완료`);
      setBulkMemoOpen(false);
      setSelectedRowKeys([]);
      fetchTransactions(page, pageSize, filters);
    } catch (err) {
      message.error(extractErrorDetail(err, "일괄 메모 변경 실패"));
    }
  };

  const handleBulkDelete = async () => {
    const ids = selectedRowKeys.map(String);
    try {
      await Promise.all(ids.map((id) => deleteTransaction(id)));
      message.success(`${ids.length}건 삭제`);
      setSelectedRowKeys([]);
      fetchTransactions(page, pageSize, filters);
    } catch (err) {
      message.error(extractErrorDetail(err, "일괄 삭제 실패"));
    }
  };

  // -------------------------------------------------------------------------
  // 컬럼 정의
  // -------------------------------------------------------------------------

  const columns: ColumnsType<Transaction> = useMemo(() => {
    const accountRender = (id: string) => {
      const acct = accountMap.get(id);
      return acct ? `${acct.bank_name} ${acct.account_number.slice(-4)}` : id.slice(0, 8);
    };

    return [
      {
        title: "거래일",
        dataIndex: "transaction_date",
        width: 110,
        sorter: (a, b) => a.transaction_date.localeCompare(b.transaction_date),
      },
      {
        title: "계좌",
        dataIndex: "account_id",
        width: 150,
        render: (id: string) => accountRender(id),
      },
      {
        title: "구분",
        dataIndex: "transaction_type",
        width: 80,
        render: (t: string) => (
          <Tag color={t === "deposit" ? "green" : "red"}>
            {t === "deposit" ? "입금" : "출금"}
          </Tag>
        ),
      },
      {
        title: "금액",
        dataIndex: "amount",
        width: 130,
        align: "right" as const,
        render: (v: string) => formatAmount(v),
        sorter: (a, b) => Number(a.amount) - Number(b.amount),
      },
      {
        title: "잔액",
        dataIndex: "balance",
        width: 130,
        align: "right" as const,
        render: (v: string | null) => formatAmount(v),
      },
      {
        title: "거래처",
        dataIndex: "counterpart_name",
        width: 150,
        ellipsis: true,
      },
      {
        title: "적요",
        dataIndex: "description",
        ellipsis: true,
      },
      {
        title: "카테고리",
        dataIndex: "category_id",
        width: 160,
        render: (_: unknown, record: Transaction) => (
          <CategoryCell
            value={record.category_id ?? null}
            categories={categories}
            onChange={(categoryId) =>
              patchTransaction(record.id, { category_id: categoryId }, "카테고리 저장")
            }
          />
        ),
      },
      {
        title: "메모",
        dataIndex: "memo",
        width: 140,
        ellipsis: true,
        render: (_: unknown, record: Transaction) => (
          <MemoCell
            key={record.memo ?? "__empty__"}
            value={record.memo}
            onSave={(memo) => patchTransaction(record.id, { memo }, "메모 저장")}
          />
        ),
      },
      {
        title: "태그",
        dataIndex: "tags",
        width: 160,
        render: (tags: string[] | null) =>
          tags && tags.length > 0 ? (
            <Space size={4} wrap>
              {tags.map((t) => (
                <Tag key={t}>{t}</Tag>
              ))}
            </Space>
          ) : (
            <Typography.Text type="secondary">-</Typography.Text>
          ),
      },
      {
        title: "첨부",
        dataIndex: "attachment_url",
        width: 70,
        align: "center" as const,
        render: (url: string | null | undefined) =>
          url ? (
            <Tooltip title="첨부 있음">
              <PaperClipOutlined style={{ color: "#1677ff" }} />
            </Tooltip>
          ) : (
            <Typography.Text type="secondary">-</Typography.Text>
          ),
      },
      {
        title: "매칭",
        dataIndex: "match_status",
        width: 130,
        render: (_: unknown, record: Transaction) => {
          const s = record.match_status;
          const color = s === "matched" ? "green" : s === "manual" ? "blue" : "default";
          const label = s === "matched" ? "매칭" : s === "manual" ? "수동" : "미매칭";
          const matchedAccount = record.matched_transaction_id
            ? "(쌍 있음)"
            : "";
          return (
            <Space size={4}>
              <Tag color={color}>{label}</Tag>
              {matchedAccount && (
                <Typography.Text type="secondary" style={{ fontSize: 11 }}>
                  {matchedAccount}
                </Typography.Text>
              )}
            </Space>
          );
        },
      },
      {
        title: "액션",
        key: "action",
        width: 200,
        fixed: "right" as const,
        render: (_: unknown, record: Transaction) => {
          if (record.is_deleted) {
            return role.isAdmin ? (
              <Button
                size="small"
                icon={<UndoOutlined />}
                onClick={() => handleRestore(record.id)}
              >
                복원
              </Button>
            ) : (
              <Tag>삭제됨</Tag>
            );
          }
          return (
            <Space size={4}>
              <Tooltip title="영수증 / 첨부">
                <Button
                  size="small"
                  type="text"
                  icon={<PaperClipOutlined />}
                  onClick={() => setAttachmentTarget(record.id)}
                />
              </Tooltip>
              {record.match_status === "unmatched" ? (
                <Tooltip title="매칭 후보">
                  <Button
                    size="small"
                    type="text"
                    icon={<LinkOutlined />}
                    onClick={() => setMatchTarget(record)}
                  />
                </Tooltip>
              ) : (
                <Tooltip title="매칭 해제">
                  <Popconfirm
                    title="매칭 해제"
                    onConfirm={() => handleRemoveMatch(record.id)}
                    okText="해제"
                    cancelText="취소"
                  >
                    <Button size="small" type="text" icon={<LinkOutlined />} danger />
                  </Popconfirm>
                </Tooltip>
              )}
              {role.isAdmin && (
                <Popconfirm
                  title="거래 삭제"
                  description="이 거래를 비활성 처리할까요?"
                  okText="삭제"
                  cancelText="취소"
                  onConfirm={() => handleDelete(record.id)}
                >
                  <Button size="small" type="text" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              )}
            </Space>
          );
        },
      },
    ];
    // patchTransaction은 useCallback으로 안정. role/categories/accountMap 의존.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accountMap, categories, patchTransaction, role.isAdmin]);

  // -------------------------------------------------------------------------
  // 행 선택
  // -------------------------------------------------------------------------

  const rowSelection: TableRowSelection<Transaction> = {
    selectedRowKeys,
    onChange: setSelectedRowKeys,
    preserveSelectedRowKeys: true,
  };

  const rowClassName = (record: Transaction): string =>
    record.is_deleted ? "tk-row-deleted" : "";

  // -------------------------------------------------------------------------
  // 렌더
  // -------------------------------------------------------------------------

  const selectedCount = selectedRowKeys.length;

  return (
    <div>
      <style>{`.tk-row-deleted { opacity: 0.45; background: #fafafa; }`}</style>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
        <h2 style={{ margin: 0 }}>거래내역</h2>
        <Space>
          <Button icon={<PlusOutlined />} type="primary" onClick={() => setCreateModal(true)}>
            거래 등록
          </Button>
          <Button icon={<UploadOutlined />} onClick={() => setUploadModal(true)}>
            엑셀 업로드
          </Button>
          <Button icon={<SyncOutlined />} onClick={handleAutoMatch}>
            자동 매칭
          </Button>
          <Button icon={<DownloadOutlined />} onClick={handleDownload}>
            엑셀 다운로드
          </Button>
        </Space>
      </div>

      {/* 필터 툴바 */}
      <Space wrap style={{ marginBottom: 8 }}>
        <Input
          placeholder="검색 (거래처, 적요)"
          prefix={<SearchOutlined />}
          allowClear
          style={{ width: 220 }}
          value={filters.keyword ?? ""}
          onChange={(e) => updateFilter("keyword", e.target.value || undefined)}
        />
        <Select
          placeholder="계좌"
          allowClear
          style={{ width: 200 }}
          value={filters.account_id}
          onChange={(v) => updateFilter("account_id", v)}
          options={accounts.map((a) => ({
            label: `${a.bank_name} ${a.account_number.slice(-4)}`,
            value: a.id,
          }))}
        />
        <Select
          placeholder="구분"
          allowClear
          style={{ width: 100 }}
          value={filters.transaction_type}
          onChange={(v: TransactionType | undefined) => updateFilter("transaction_type", v)}
          options={[
            { label: "입금", value: "deposit" },
            { label: "출금", value: "withdrawal" },
          ]}
        />
        <Select
          placeholder="매칭상태"
          allowClear
          style={{ width: 120 }}
          value={filters.match_status}
          onChange={(v: MatchStatus | undefined) => updateFilter("match_status", v)}
          options={[
            { label: "미매칭", value: "unmatched" },
            { label: "자동", value: "matched" },
            { label: "수동", value: "manual" },
          ]}
        />
        <RangePicker
          value={
            filters.date_from && filters.date_to
              ? [dayjs(filters.date_from), dayjs(filters.date_to)]
              : null
          }
          onChange={(range: [Dayjs | null, Dayjs | null] | null) => {
            setPage(1);
            setFilters((prev) => {
              const next = { ...prev };
              if (range && range[0] && range[1]) {
                next.date_from = range[0].format("YYYY-MM-DD");
                next.date_to = range[1].format("YYYY-MM-DD");
              } else {
                delete next.date_from;
                delete next.date_to;
              }
              return next;
            });
          }}
        />
      </Space>

      <Space wrap style={{ marginBottom: 16 }}>
        <InputNumber
          placeholder="금액 최소"
          style={{ width: 130 }}
          min={0}
          value={filters.amount_min ?? null}
          onChange={(v) => updateFilter("amount_min", v ?? undefined)}
          formatter={(v) => (v == null ? "" : `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ","))}
        />
        <InputNumber
          placeholder="금액 최대"
          style={{ width: 130 }}
          min={0}
          value={filters.amount_max ?? null}
          onChange={(v) => updateFilter("amount_max", v ?? undefined)}
          formatter={(v) => (v == null ? "" : `${v}`.replace(/\B(?=(\d{3})+(?!\d))/g, ","))}
        />
        <Select
          placeholder="카테고리"
          allowClear
          style={{ width: 180 }}
          value={filters.category_id}
          onChange={(v) => updateFilter("category_id", v)}
          options={categories.map((c) => ({ label: c.name, value: c.id }))}
          showSearch
          optionFilterProp="label"
        />
        <AutoComplete
          placeholder="거래처 자동완성"
          style={{ width: 200 }}
          allowClear
          value={counterpartQuery}
          options={counterpartOptions.map((c) => ({
            value: c.counterpart_id ?? c.name,
            label: `${c.name} (${c.count})`,
          }))}
          onSearch={setCounterpartQuery}
          onChange={(v) => setCounterpartQuery(v ?? "")}
          onSelect={(value, option) => {
            const picked = counterpartOptions.find(
              (c) => (c.counterpart_id ?? c.name) === value,
            );
            if (picked?.counterpart_id) {
              updateFilter("counterpart_id", picked.counterpart_id);
            } else if (picked) {
              updateFilter("keyword", picked.name);
            }
            setCounterpartQuery(option.label as string);
          }}
          onClear={() => {
            updateFilter("counterpart_id", undefined);
            setCounterpartQuery("");
          }}
        />
        <Space>
          <Typography.Text type="secondary">비활성 포함</Typography.Text>
          <Switch
            checked={!!filters.include_deleted}
            onChange={(checked) =>
              updateFilter("include_deleted", checked ? true : undefined)
            }
          />
        </Space>
        <Button icon={<ReloadOutlined />} onClick={resetFilters}>필터 초기화</Button>
      </Space>

      {/* 일괄 작업 바 */}
      {selectedCount > 0 && (
        <div
          style={{
            background: "#f0f5ff",
            border: "1px solid #adc6ff",
            padding: "8px 12px",
            borderRadius: 6,
            marginBottom: 12,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <Typography.Text strong>{selectedCount}건 선택됨</Typography.Text>
          <Space>
            <Button size="small" onClick={() => setBulkCategoryOpen(true)}>
              일괄 카테고리
            </Button>
            <Button size="small" onClick={() => setBulkMemoOpen(true)}>
              일괄 메모
            </Button>
            {role.isAdmin && (
              <Popconfirm
                title="선택 거래 일괄 삭제"
                description={`${selectedCount}건을 비활성 처리할까요?`}
                onConfirm={handleBulkDelete}
                okText="삭제"
                cancelText="취소"
              >
                <Button size="small" danger>
                  일괄 삭제 (admin)
                </Button>
              </Popconfirm>
            )}
            <Button size="small" type="link" onClick={() => setSelectedRowKeys([])}>
              선택 해제
            </Button>
          </Space>
        </div>
      )}

      <Table<Transaction>
        rowSelection={rowSelection}
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        size="middle"
        rowClassName={rowClassName}
        pagination={{
          current: page,
          pageSize,
          total,
          showSizeChanger: true,
          pageSizeOptions: [20, 50, 100, 200],
          showTotal: (t) => `총 ${t.toLocaleString("ko-KR")}건`,
          onChange: (nextPage, nextSize) => {
            setPage(nextPage);
            setPageSize(nextSize);
          },
        }}
        scroll={{ x: 1700 }}
      />

      {/* 카테고리 미사용 경고 (필터 검색 결과 보조) */}
      {categories.length === 0 && (
        <Typography.Paragraph type="secondary" style={{ marginTop: 8 }}>
          카테고리 마스터가 비어 있습니다. /api/categories 가 활성화되면 자동으로 표시됩니다.
        </Typography.Paragraph>
      )}
      {categoryMap.size === 0 && null}

      {/* 모달 영역 */}
      <TransactionFormModal
        open={createModal}
        loading={creating}
        accounts={accounts}
        categories={categories}
        defaultAccountId={filters.account_id}
        onCancel={() => setCreateModal(false)}
        onSubmit={handleCreate}
      />

      <AttachmentModal
        open={attachmentTarget !== null}
        transactionId={attachmentTarget}
        onClose={() => {
          setAttachmentTarget(null);
          fetchTransactions(page, pageSize, filters);
        }}
      />

      <MatchingCandidatesModal
        open={matchTarget !== null}
        source={matchTarget}
        accounts={accounts}
        onClose={() => setMatchTarget(null)}
        onMatched={() => fetchTransactions(page, pageSize, filters)}
      />

      <BulkCategoryModal
        key={`bulk-cat-${bulkCategoryOpen ? "open" : "closed"}`}
        open={bulkCategoryOpen}
        count={selectedCount}
        categories={categories}
        onCancel={() => setBulkCategoryOpen(false)}
        onConfirm={handleBulkCategory}
      />

      <BulkMemoModal
        key={`bulk-memo-${bulkMemoOpen ? "open" : "closed"}`}
        open={bulkMemoOpen}
        count={selectedCount}
        onCancel={() => setBulkMemoOpen(false)}
        onConfirm={handleBulkMemo}
      />

      <Modal
        title="거래내역 엑셀 업로드"
        open={uploadModal}
        onCancel={() => setUploadModal(false)}
        footer={null}
        destroyOnClose
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <Select
            placeholder="업로드할 계좌 선택"
            style={{ width: "100%" }}
            value={uploadAccountId || undefined}
            onChange={setUploadAccountId}
            options={accounts.map((a) => ({
              label: `${a.bank_name} ${a.account_number}`,
              value: a.id,
            }))}
          />
          <Upload.Dragger
            accept=".xlsx,.xls"
            showUploadList={false}
            beforeUpload={(file) => handleExcelUpload(file as File)}
          >
            <p style={{ padding: "20px 0" }}>엑셀 파일을 드래그하거나 클릭하여 업로드</p>
          </Upload.Dragger>
        </Space>
      </Modal>
    </div>
  );
}
