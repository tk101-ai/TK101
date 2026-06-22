import { useMemo } from "react";
import { Button, Space, Table, Typography } from "antd";
import {
  DownloadOutlined,
  PlusOutlined,
  SyncOutlined,
  UploadOutlined,
} from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import type { TableRowSelection } from "antd/es/table/interface";
import { type Transaction } from "../api/transactions";
import { useAuth } from "../hooks/useAuth";
import TransactionFormModal from "../components/finance/TransactionFormModal";
import AttachmentModal from "../components/finance/AttachmentModal";
import MatchingCandidatesModal from "../components/finance/MatchingCandidatesModal";
import { type RoleBased } from "./finance/transactions/types";
import { useTransactions } from "./finance/transactions/useTransactions";
import { buildTransactionColumns } from "./finance/transactions/transactionColumns";
import { TransactionFilters } from "./finance/transactions/TransactionFilters";
import { TransactionBulkBar } from "./finance/transactions/TransactionBulkBar";
import { UploadModal } from "./finance/transactions/UploadModal";
import { BulkCategoryModal, BulkMemoModal } from "./finance/transactions/BulkModals";

// ---------------------------------------------------------------------------
// 메인 페이지
// ---------------------------------------------------------------------------

export default function Transactions() {
  const { user } = useAuth();
  const role: RoleBased = { isAdmin: user?.role === "admin" };

  const tx = useTransactions();
  const {
    data,
    accounts,
    categories,
    loading,
    total,
    page,
    pageSize,
    filters,
    accountMap,
    categoryMap,
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
    setPage,
    setPageSize,
    setFilters,
    fetchTransactions,
    updateFilter,
    resetFilters,
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
  } = tx;

  // -------------------------------------------------------------------------
  // 컬럼 정의
  // -------------------------------------------------------------------------

  const columns: ColumnsType<Transaction> = useMemo(() => {
    return buildTransactionColumns({
      accountMap,
      categories,
      patchTransaction,
      isAdmin: role.isAdmin,
      onRestore: handleRestore,
      onAttachment: setAttachmentTarget,
      onMatch: setMatchTarget,
      onRemoveMatch: handleRemoveMatch,
      onDelete: handleDelete,
    });
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

      <TransactionFilters
        filters={filters}
        accounts={accounts}
        categories={categories}
        counterpartOptions={counterpartOptions}
        counterpartQuery={counterpartQuery}
        setCounterpartQuery={setCounterpartQuery}
        updateFilter={updateFilter}
        setPage={setPage}
        setFilters={setFilters}
        resetFilters={resetFilters}
      />

      {selectedCount > 0 && (
        <TransactionBulkBar
          selectedCount={selectedCount}
          isAdmin={role.isAdmin}
          onBulkCategory={() => setBulkCategoryOpen(true)}
          onBulkMemo={() => setBulkMemoOpen(true)}
          onBulkDelete={handleBulkDelete}
          onClearSelection={() => setSelectedRowKeys([])}
        />
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

      <UploadModal
        open={uploadModal}
        accounts={accounts}
        uploadAccountId={uploadAccountId}
        setUploadAccountId={setUploadAccountId}
        onCancel={() => setUploadModal(false)}
        onUpload={handleExcelUpload}
      />
    </div>
  );
}
