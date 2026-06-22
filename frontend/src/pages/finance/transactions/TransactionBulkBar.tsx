import { Button, Popconfirm, Space, Typography } from "antd";

// ---------------------------------------------------------------------------
// 일괄 작업 바
// ---------------------------------------------------------------------------

interface TransactionBulkBarProps {
  selectedCount: number;
  isAdmin: boolean;
  onBulkCategory: () => void;
  onBulkMemo: () => void;
  onBulkDelete: () => void;
  onClearSelection: () => void;
}

export function TransactionBulkBar({
  selectedCount,
  isAdmin,
  onBulkCategory,
  onBulkMemo,
  onBulkDelete,
  onClearSelection,
}: TransactionBulkBarProps) {
  return (
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
        <Button size="small" onClick={onBulkCategory}>
          일괄 카테고리
        </Button>
        <Button size="small" onClick={onBulkMemo}>
          일괄 메모
        </Button>
        {isAdmin && (
          <Popconfirm
            title="선택 거래 일괄 삭제"
            description={`${selectedCount}건을 비활성 처리할까요?`}
            onConfirm={onBulkDelete}
            okText="삭제"
            cancelText="취소"
          >
            <Button size="small" danger>
              일괄 삭제 (admin)
            </Button>
          </Popconfirm>
        )}
        <Button size="small" type="link" onClick={onClearSelection}>
          선택 해제
        </Button>
      </Space>
    </div>
  );
}
