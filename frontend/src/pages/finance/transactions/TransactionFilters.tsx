import {
  AutoComplete,
  Button,
  DatePicker,
  Input,
  InputNumber,
  Select,
  Space,
  Switch,
  Typography,
} from "antd";
import { ReloadOutlined, SearchOutlined } from "@ant-design/icons";
import dayjs, { Dayjs } from "dayjs";
import {
  type CounterpartSuggestion,
  type MatchStatus,
  type TransactionFilter,
  type TransactionType,
} from "../../../api/transactions";
import { type CategoryRead } from "../../../api/categories";
import { type Account } from "../../../api/accounts";

const { RangePicker } = DatePicker;

type Filters = Omit<TransactionFilter, "limit" | "offset">;

interface TransactionFiltersProps {
  filters: Filters;
  accounts: Account[];
  categories: CategoryRead[];
  counterpartOptions: CounterpartSuggestion[];
  counterpartQuery: string;
  setCounterpartQuery: (q: string) => void;
  updateFilter: <K extends keyof Filters>(key: K, value: Filters[K] | undefined) => void;
  setPage: (page: number) => void;
  setFilters: React.Dispatch<React.SetStateAction<Filters>>;
  resetFilters: () => void;
}

export function TransactionFilters({
  filters,
  accounts,
  categories,
  counterpartOptions,
  counterpartQuery,
  setCounterpartQuery,
  updateFilter,
  setPage,
  setFilters,
  resetFilters,
}: TransactionFiltersProps) {
  return (
    <>
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
    </>
  );
}
