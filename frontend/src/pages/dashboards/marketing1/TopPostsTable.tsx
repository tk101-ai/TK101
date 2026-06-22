import { Button, Card, Select, Space, Table, Tag } from "antd";
import { LinkOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import {
  LANGUAGE_LABELS,
  LANGUAGE_OPTIONS,
  PLATFORM_LABELS,
  PLATFORM_OPTIONS,
  formatNumber,
} from "./constants";
import type { TopPost } from "./types";

interface TopPostsTableProps {
  topPosts: TopPost[];
  topLanguage: string;
  setTopLanguage: (val: string) => void;
  topPlatform: string;
  setTopPlatform: (val: string) => void;
}

const topPostColumns: ColumnsType<TopPost> = [
  {
    title: "발행일",
    dataIndex: "posted_at",
    key: "posted_at",
    width: 120,
    render: (val: string) => (val ? dayjs(val).format("YYYY-MM-DD") : "-"),
  },
  {
    title: "어권",
    dataIndex: "language",
    key: "language",
    width: 90,
    render: (val: string) => (
      <Tag color="geekblue" style={{ margin: 0 }}>
        {LANGUAGE_LABELS[val] ?? val}
      </Tag>
    ),
  },
  {
    title: "플랫폼",
    dataIndex: "platform",
    key: "platform",
    width: 110,
    render: (val: string) => (
      <Tag color="purple" style={{ margin: 0 }}>
        {PLATFORM_LABELS[val] ?? val}
      </Tag>
    ),
  },
  {
    title: "제목",
    dataIndex: "title",
    key: "title",
    ellipsis: true,
    render: (val: string) => val ?? "-",
  },
  {
    title: "조회수",
    dataIndex: "view_count",
    key: "view_count",
    width: 110,
    align: "right",
    render: (val: number) => formatNumber(val),
  },
  {
    title: "반응수",
    dataIndex: "total_engagement",
    key: "total_engagement",
    width: 110,
    align: "right",
    render: (val: number) => formatNumber(val),
  },
  {
    title: "",
    dataIndex: "url",
    key: "url",
    width: 80,
    align: "center",
    render: (val: string) =>
      val ? (
        <Button
          type="link"
          size="small"
          icon={<LinkOutlined />}
          onClick={() => window.open(val, "_blank", "noopener,noreferrer")}
        >
          보기
        </Button>
      ) : (
        "-"
      ),
  },
];

export default function TopPostsTable({
  topPosts,
  topLanguage,
  setTopLanguage,
  topPlatform,
  setTopPlatform,
}: TopPostsTableProps) {
  return (
    <Card
      title="인기 콘텐츠 Top 5"
      style={{ marginBottom: 16 }}
      extra={
        <Space size="small">
          <Select
            value={topLanguage}
            options={LANGUAGE_OPTIONS}
            onChange={(val) => setTopLanguage(val)}
            style={{ width: 130 }}
            aria-label="어권 필터"
          />
          <Select
            value={topPlatform}
            options={PLATFORM_OPTIONS}
            onChange={(val) => setTopPlatform(val)}
            style={{ width: 140 }}
            aria-label="플랫폼 필터"
          />
        </Space>
      }
    >
      <Table<TopPost>
        columns={topPostColumns}
        dataSource={topPosts}
        rowKey="id"
        pagination={false}
        size="middle"
        scroll={{ x: 760 }}
        locale={{ emptyText: "데이터가 없습니다" }}
      />
    </Card>
  );
}
