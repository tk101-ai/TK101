import { useMemo } from "react";
import { Card, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { LANGUAGE_LABELS, PLATFORM_LABELS, formatNumber } from "./constants";
import type { PivotedRow } from "./types";

interface WeeklyKpiTableProps {
  year: number;
  month: number;
  weekNumbers: number[];
  pivotedRows: PivotedRow[];
  totalRow: PivotedRow;
}

export default function WeeklyKpiTable({
  year,
  month,
  weekNumbers,
  pivotedRows,
  totalRow,
}: WeeklyKpiTableProps) {
  const weeklyColumns: ColumnsType<PivotedRow> = useMemo(() => {
    const weekColumns: ColumnsType<PivotedRow> = weekNumbers.map((w) => ({
      title: `${w}주 팔로워`,
      key: `week${w}`,
      align: "right",
      render: (_: unknown, record) => formatNumber(record.weeks[w] ?? 0),
    }));
    return [
      {
        title: "어권",
        dataIndex: "language",
        key: "language",
        width: 90,
        render: (val: string) =>
          val === "__total__" ? (
            <strong>합계</strong>
          ) : (
            <Tag color="geekblue" style={{ margin: 0 }}>
              {LANGUAGE_LABELS[val] ?? val}
            </Tag>
          ),
        onCell: (record) =>
          record.key === "__total__" ? { colSpan: 2 } : { colSpan: 1 },
      },
      {
        title: "플랫폼",
        dataIndex: "platform",
        key: "platform",
        width: 110,
        render: (val: string, record) =>
          record.key === "__total__" ? null : (
            <span style={{ fontWeight: 500 }}>
              {PLATFORM_LABELS[val] ?? val}
            </span>
          ),
        onCell: (record) =>
          record.key === "__total__" ? { colSpan: 0 } : { colSpan: 1 },
      },
      ...weekColumns,
      {
        title: "콘텐츠수",
        dataIndex: "postCount",
        key: "postCount",
        align: "right",
        render: (val: number) => formatNumber(val),
      },
      {
        title: "조회수",
        dataIndex: "viewCount",
        key: "viewCount",
        align: "right",
        render: (val: number) => formatNumber(val),
      },
      {
        title: "반응수",
        dataIndex: "reactionCount",
        key: "reactionCount",
        align: "right",
        render: (val: number) => formatNumber(val),
      },
    ];
  }, [weekNumbers]);

  const tableData = pivotedRows.length > 0 ? [...pivotedRows, totalRow] : [];

  return (
    <Card
      title="주간 KPI"
      extra={
        <span style={{ color: "rgba(0,0,0,0.45)", fontSize: 13 }}>
          {year}년 {month}월
        </span>
      }
      style={{ marginBottom: 16 }}
    >
      <Table<PivotedRow>
        columns={weeklyColumns}
        dataSource={tableData}
        rowKey="key"
        pagination={false}
        size="middle"
        scroll={{ x: 900 }}
        locale={{ emptyText: "데이터가 없습니다" }}
        rowClassName={(record) =>
          record.key === "__total__" ? "tk101-total-row" : ""
        }
      />
      <style>{`
        .tk101-total-row td {
          background: #fafafa !important;
          font-weight: 700;
        }
      `}</style>
    </Card>
  );
}
