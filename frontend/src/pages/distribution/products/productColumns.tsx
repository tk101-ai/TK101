import { Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { ProductOut } from "../../../api/distribution";
import { getBrandColor, getCategoryColor } from "./colors";
import { formatAmount, formatDate, formatNumber } from "./format";

const { Text } = Typography;

export const productColumns: ColumnsType<ProductOut> = [
  {
    title: "회사",
    dataIndex: "company_label",
    width: 110,
    fixed: "left",
    render: (v: string | null | undefined) =>
      v ? <Tag color="geekblue">{v}</Tag> : <Text type="secondary">—</Text>,
  },
  {
    title: "브랜드",
    dataIndex: "brand",
    width: 140,
    render: (v: string) => <Tag color={getBrandColor(v)}>{v}</Tag>,
  },
  {
    title: "제품명(영문)",
    dataIndex: "product_name_en",
    width: 240,
    render: (v: string | null) =>
      v ? <Text>{v}</Text> : <Text type="secondary">—</Text>,
  },
  {
    title: "제품코드",
    dataIndex: "product_code",
    width: 160,
    render: (v: string | null) =>
      v ? (
        <Text style={{ fontFamily: "monospace", fontSize: 12 }}>{v}</Text>
      ) : (
        <Text type="secondary">—</Text>
      ),
  },
  {
    title: "카테고리",
    dataIndex: "category",
    width: 110,
    render: (v: string | null) =>
      v ? (
        <Tag color={getCategoryColor(v)}>{v}</Tag>
      ) : (
        <Text type="secondary">—</Text>
      ),
  },
  {
    title: "매입수량",
    dataIndex: "purchase_qty",
    width: 100,
    align: "right" as const,
    render: (v: number | null) => (
      <span style={{ fontVariantNumeric: "tabular-nums" }}>
        {formatNumber(v)}
      </span>
    ),
  },
  {
    title: "국내재고",
    dataIndex: "domestic_stock_qty",
    width: 100,
    align: "right" as const,
    render: (v: number | null) => (
      <span style={{ fontVariantNumeric: "tabular-nums" }}>
        {formatNumber(v)}
      </span>
    ),
  },
  {
    title: "VN재고이동",
    dataIndex: "vn_inventory_move_qty",
    width: 110,
    align: "right" as const,
    render: (v: number | null) => (
      <span style={{ fontVariantNumeric: "tabular-nums", color: "#722ed1" }}>
        {formatNumber(v)}
      </span>
    ),
  },
  {
    title: "VN매출완료",
    dataIndex: "vn_sales_completed_qty",
    width: 110,
    align: "right" as const,
    render: (v: number | null) => (
      <span style={{ fontVariantNumeric: "tabular-nums", color: "#fa8c16" }}>
        {formatNumber(v)}
      </span>
    ),
  },
  {
    title: "VN현지재고",
    dataIndex: "vn_local_stock_qty",
    width: 110,
    align: "right" as const,
    render: (v: number | null) => (
      <span style={{ fontVariantNumeric: "tabular-nums", color: "#13c2c2" }}>
        {formatNumber(v)}
      </span>
    ),
  },
  {
    title: "매입금액",
    dataIndex: "purchase_price",
    width: 140,
    align: "right" as const,
    render: (v: string | null) => (
      <span
        style={{
          fontFamily: "monospace",
          fontSize: 13,
          fontVariantNumeric: "tabular-nums",
        }}
      >
        {formatAmount(v)}
      </span>
    ),
  },
  {
    title: "매입일",
    dataIndex: "purchase_date",
    width: 110,
    render: (v: string | null) => (
      <Text style={{ fontSize: 12 }}>{formatDate(v)}</Text>
    ),
  },
  {
    title: "승인번호",
    dataIndex: "approval_number",
    width: 140,
    render: (v: string | null) =>
      v ? (
        <Text style={{ fontFamily: "monospace", fontSize: 12 }}>{v}</Text>
      ) : (
        <Text type="secondary">—</Text>
      ),
  },
];
