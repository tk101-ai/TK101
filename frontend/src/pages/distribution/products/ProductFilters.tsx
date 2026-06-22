import { Input, Select } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import type { FilterOption } from "./useProducts";

interface ProductFiltersProps {
  searchInput: string;
  onSearchChange: (v: string) => void;
  brandFilter: string;
  onBrandChange: (v: string) => void;
  brandOptions: FilterOption[];
  categoryFilter: string;
  onCategoryChange: (v: string) => void;
  categoryOptions: FilterOption[];
}

export function ProductFilters({
  searchInput,
  onSearchChange,
  brandFilter,
  onBrandChange,
  brandOptions,
  categoryFilter,
  onCategoryChange,
  categoryOptions,
}: ProductFiltersProps) {
  return (
    <div
      style={{
        display: "flex",
        gap: 12,
        flexWrap: "wrap",
        marginBottom: 16,
      }}
    >
      <Input
        placeholder="제품명·제품코드 검색"
        prefix={<SearchOutlined />}
        allowClear
        style={{ width: 260 }}
        value={searchInput}
        onChange={(e) => onSearchChange(e.target.value)}
      />
      <Select
        value={brandFilter}
        onChange={onBrandChange}
        options={brandOptions}
        style={{ width: 200 }}
        showSearch
        optionFilterProp="label"
      />
      <Select
        value={categoryFilter}
        onChange={onCategoryChange}
        options={categoryOptions}
        style={{ width: 180 }}
        showSearch
        optionFilterProp="label"
      />
    </div>
  );
}
