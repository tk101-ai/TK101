import { useCallback, useEffect, useState } from "react";
import { DatePicker, Input, message, Select, Space, Table, Tag } from "antd";
import { SearchOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import { Button } from "antd";
import { getTaxInvoices, type TaxInvoice, type TaxInvoiceFilter } from "../api/taxInvoices";

const { RangePicker } = DatePicker;

// 필터 변경 시 자동 재조회 debounce (ms). keyword 입력 타이핑 대응.
const REFETCH_DEBOUNCE_MS = 300;

/** 금액 문자열을 "1,234원"으로 렌더. null/빈값/NaN은 "-" 표기. */
function formatAmount(v: string | null | undefined): string {
  if (v == null || v === "") return "-";
  const n = Number(v);
  if (!Number.isFinite(n)) return "-";
  return n.toLocaleString("ko-KR") + "원";
}

export default function TaxInvoices() {
  const [data, setData] = useState<TaxInvoice[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState<TaxInvoiceFilter>({});

  const fetchData = useCallback(async (currentFilters: TaxInvoiceFilter) => {
    setLoading(true);
    try {
      const res = await getTaxInvoices(currentFilters);
      setData(res.data);
    } catch {
      message.error("세금계산서 조회 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  // 필터 변경 시 debounce + 자동 재조회 (Transactions 와 동일 UX).
  // selects/date 는 즉시 변경되고, keyword 타이핑은 debounce 로 흡수된다.
  useEffect(() => {
    const handle = window.setTimeout(() => {
      void fetchData(filters);
    }, REFETCH_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [filters, fetchData]);

  const handleSearch = () => void fetchData(filters);

  const columns: ColumnsType<TaxInvoice> = [
    {
      title: "구분",
      dataIndex: "invoice_type",
      width: 80,
      render: (t: string) => (
        <Tag color={t === "purchase" ? "blue" : "orange"}>
          {t === "purchase" ? "매입" : "매출"}
        </Tag>
      ),
    },
    {
      title: "발행일",
      dataIndex: "issue_date",
      width: 110,
      sorter: (a, b) => a.issue_date.localeCompare(b.issue_date),
    },
    {
      title: "세금계산서번호",
      dataIndex: "invoice_number",
      width: 160,
    },
    {
      title: "공급자",
      dataIndex: "supplier_name",
      width: 150,
      ellipsis: true,
    },
    {
      title: "공급받는자",
      dataIndex: "buyer_name",
      width: 150,
      ellipsis: true,
    },
    {
      title: "공급가액",
      dataIndex: "supply_amount",
      width: 130,
      align: "right" as const,
      render: (v: string) => formatAmount(v),
      sorter: (a, b) => Number(a.supply_amount) - Number(b.supply_amount),
    },
    {
      title: "세액",
      dataIndex: "tax_amount",
      width: 120,
      align: "right" as const,
      render: (v: string) => formatAmount(v),
    },
    {
      title: "합계",
      dataIndex: "total_amount",
      width: 130,
      align: "right" as const,
      render: (v: string) => formatAmount(v),
      sorter: (a, b) => Number(a.total_amount) - Number(b.total_amount),
    },
    {
      title: "매칭상태",
      dataIndex: "match_status",
      width: 100,
      render: (s: string) => {
        const color = s === "matched" ? "green" : s === "manual" ? "blue" : "red";
        const label = s === "matched" ? "매칭" : s === "manual" ? "수동" : "미매칭";
        return <Tag color={color}>{label}</Tag>;
      },
    },
    {
      title: "메모",
      dataIndex: "memo",
      width: 120,
      ellipsis: true,
      render: (memo: string | null) => memo || "-",
    },
  ];

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>세금계산서</h2>

      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          placeholder="구분"
          allowClear
          style={{ width: 120 }}
          onChange={(v) => setFilters((f) => ({ ...f, invoice_type: v }))}
          options={[
            { label: "매입", value: "purchase" },
            { label: "매출", value: "sales" },
          ]}
        />
        <RangePicker
          onChange={(_, dates) =>
            setFilters((f) => ({
              ...f,
              date_from: dates[0] || undefined,
              date_to: dates[1] || undefined,
            }))
          }
        />
        <Input
          placeholder="검색 (공급자, 공급받는자, 번호)"
          prefix={<SearchOutlined />}
          style={{ width: 250 }}
          onChange={(e) => setFilters((f) => ({ ...f, keyword: e.target.value }))}
          onPressEnter={handleSearch}
        />
        <Select
          placeholder="매칭상태"
          allowClear
          style={{ width: 120 }}
          onChange={(v) => setFilters((f) => ({ ...f, match_status: v }))}
          options={[
            { label: "미매칭", value: "unmatched" },
            { label: "매칭", value: "matched" },
            { label: "수동", value: "manual" },
          ]}
        />
        <Button type="primary" icon={<SearchOutlined />} onClick={handleSearch}>
          조회
        </Button>
      </Space>

      <Table
        columns={columns}
        dataSource={data}
        rowKey="id"
        loading={loading}
        size="middle"
        pagination={{
          pageSize: 50,
          showSizeChanger: true,
          showTotal: (t) => "총 " + t + "건",
        }}
        scroll={{ x: 1300 }}
      />
    </div>
  );
}
