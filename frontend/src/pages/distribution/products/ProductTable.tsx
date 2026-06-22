import { Table } from "antd";
import type { ProductOut } from "../../../api/distribution";
import { productColumns } from "./productColumns";

interface ProductTableProps {
  data: ProductOut[];
  loading: boolean;
}

export function ProductTable({ data, loading }: ProductTableProps) {
  return (
    <Table
      columns={productColumns}
      dataSource={data}
      rowKey="id"
      loading={loading}
      size="middle"
      scroll={{ x: 1830 }}
      pagination={{
        pageSize: 50,
        showSizeChanger: true,
        pageSizeOptions: [20, 50, 100, 200],
        showTotal: (t) => `총 ${t}건`,
      }}
    />
  );
}
