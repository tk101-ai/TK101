import { useState } from "react";
import { Form, Input, Modal, Select } from "antd";
import { type CategoryRead } from "../../../api/categories";

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

export function BulkCategoryModal({
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

export function BulkMemoModal({ open, count, onCancel, onConfirm }: BulkMemoModalProps) {
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
