import { useCallback, useEffect, useMemo, useState } from "react";
import { message } from "antd";
import dayjs from "dayjs";
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
  type Transaction,
  type TransactionCreate,
  type TransactionFilter,
  type TransactionUpdate,
} from "../../../api/transactions";
import { listCategoriesFlat, type CategoryRead } from "../../../api/categories";
import { listAccounts, type Account } from "../../../api/accounts";
import { extractErrorDetail } from "../../../utils/errorUtils";
import { triggerBlobDownload } from "../../../utils/download";
import { runBatched, type BatchResult } from "../../../utils/concurrency";
import { DEFAULT_PAGE_SIZE } from "./types";

type Filters = Omit<TransactionFilter, "limit" | "offset">;

export function useTransactions() {
  const [data, setData] = useState<Transaction[]>([]);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [categories, setCategories] = useState<CategoryRead[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);

  // 페이지네이션 (서버 페이징)
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);

  // 필터 (debounce 적용)
  const [filters, setFilters] = useState<Filters>({});

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

  // -------------------------------------------------------------------------
  // 데이터 로드
  // -------------------------------------------------------------------------

  const fetchTransactions = useCallback(
    async (
      currentPage: number,
      currentSize: number,
      currentFilters: Filters,
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

  const updateFilter = <K extends keyof Filters>(
    key: K,
    value: Filters[K] | undefined,
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
      void fetchTransactions(page, pageSize, filters);
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
      void fetchTransactions(page, pageSize, filters);
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
      void fetchTransactions(page, pageSize, filters);
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
      void fetchTransactions(page, pageSize, filters);
    } catch (err) {
      message.error(extractErrorDetail(err, "삭제 실패"));
    }
  };

  const handleRestore = async (id: string) => {
    try {
      await restoreTransaction(id);
      message.success("복원 완료");
      void fetchTransactions(page, pageSize, filters);
    } catch (err) {
      message.error(extractErrorDetail(err, "복원 실패"));
    }
  };

  const handleRemoveMatch = async (id: string) => {
    try {
      await removeMatch(id);
      message.success("매칭 해제");
      void fetchTransactions(page, pageSize, filters);
    } catch (err) {
      message.error(extractErrorDetail(err, "매칭 해제 실패"));
    }
  };

  // 일괄 작업 결과(부분 성공 포함)를 사용자에게 보고.
  // 전용 일괄 엔드포인트가 생기면 단일 요청으로 대체 가능(현재는 행별 PATCH 를
  // 동시성 상한으로 묶어 실행 + 부분 성공 집계).
  const reportBulkResult = (result: BatchResult, action: string) => {
    const { succeeded, failed } = result;
    if (failed === 0) {
      message.success(`${succeeded}건 ${action} 완료`);
    } else if (succeeded === 0) {
      message.error(`${action} 실패 (${failed}건)`);
    } else {
      message.warning(`${action} 부분 완료 (성공 ${succeeded}건 / 실패 ${failed}건)`);
    }
  };

  const handleBulkCategory = async (categoryId: string | null) => {
    const ids = selectedRowKeys.map(String);
    const result = await runBatched(ids, (id) =>
      updateTransaction(id, { category_id: categoryId }),
    );
    reportBulkResult(result, "카테고리 변경");
    setBulkCategoryOpen(false);
    setSelectedRowKeys([]);
    void fetchTransactions(page, pageSize, filters);
  };

  const handleBulkMemo = async (memo: string | null) => {
    const ids = selectedRowKeys.map(String);
    const result = await runBatched(ids, (id) =>
      updateTransaction(id, { memo }),
    );
    reportBulkResult(result, "메모 변경");
    setBulkMemoOpen(false);
    setSelectedRowKeys([]);
    void fetchTransactions(page, pageSize, filters);
  };

  const handleBulkDelete = async () => {
    const ids = selectedRowKeys.map(String);
    const result = await runBatched(ids, (id) => deleteTransaction(id));
    reportBulkResult(result, "삭제");
    setSelectedRowKeys([]);
    void fetchTransactions(page, pageSize, filters);
  };

  return {
    // 데이터/상태
    data,
    accounts,
    categories,
    loading,
    total,
    page,
    pageSize,
    filters,
    accountMap,
    // 모달/UI 상태
    uploadModal,
    setUploadModal,
    uploadAccountId,
    setUploadAccountId,
    createModal,
    setCreateModal,
    creating,
    attachmentTarget,
    setAttachmentTarget,
    matchTarget,
    setMatchTarget,
    selectedRowKeys,
    setSelectedRowKeys,
    bulkCategoryOpen,
    setBulkCategoryOpen,
    bulkMemoOpen,
    setBulkMemoOpen,
    counterpartOptions,
    counterpartQuery,
    setCounterpartQuery,
    // 페이지 setter
    setPage,
    setPageSize,
    setFilters,
    // 데이터 로드/필터
    fetchTransactions,
    updateFilter,
    resetFilters,
    // 액션 핸들러
    handleDownload,
    handleAutoMatch,
    handleExcelUpload,
    handleCreate,
    patchTransaction,
    handleDelete,
    handleRestore,
    handleRemoveMatch,
    handleBulkCategory,
    handleBulkMemo,
    handleBulkDelete,
  };
}
