import { useMemo, useState } from "react";
import { Select } from "antd";
import { type CategoryRead } from "../../../api/categories";

// ---------------------------------------------------------------------------
// 인라인 카테고리 셀
// ---------------------------------------------------------------------------

interface CategoryCellProps {
  value: string | null | undefined;
  categories: CategoryRead[];
  onChange: (categoryId: string | null) => Promise<void> | void;
}

export function CategoryCell({ value, categories, onChange }: CategoryCellProps) {
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
