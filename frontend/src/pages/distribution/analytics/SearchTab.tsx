import { useCallback, useState } from "react";
import { Link } from "react-router-dom";
import {
  Button,
  Card,
  Empty,
  Input,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { SearchOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import {
  searchMessages,
  type MessageSearchItem,
} from "../../../api/distribution_analytics";
import { extractErrorDetail } from "../../../utils/errorUtils";
import { formatDateTime } from "./format";
import { MESSAGE_STATUS_COLOR } from "./constants";
import type { RangeFilter } from "./types";

const { Text } = Typography;

interface SearchTabProps {
  filter: RangeFilter;
}

export function SearchTab({ filter }: SearchTabProps) {
  const [query, setQuery] = useState<string>("");
  const [results, setResults] = useState<MessageSearchItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);

  const handleSearch = useCallback(
    async (value: string) => {
      const trimmed = value.trim();
      if (!trimmed) {
        message.warning("검색어를 입력하세요");
        return;
      }
      setLoading(true);
      setHasSearched(true);
      try {
        const items = await searchMessages(trimmed, filter.from, filter.to, 200);
        setResults(items);
        if (items.length === 0) {
          message.info("검색 결과가 없습니다");
        }
      } catch (err: unknown) {
        message.error(extractErrorDetail(err, "메시지 검색 실패"));
      } finally {
        setLoading(false);
      }
    },
    [filter.from, filter.to],
  );

  const columns: ColumnsType<MessageSearchItem> = [
    {
      title: "시나리오",
      dataIndex: "scenario_name",
      width: 180,
      render: (v: string) => <Tag color="purple">{v}</Tag>,
    },
    {
      title: "발신자",
      dataIndex: "sender_account_label",
      width: 120,
      render: (v: string) => <Tag color="geekblue">{v}</Tag>,
    },
    {
      title: "메시지 내용",
      dataIndex: "content",
      ellipsis: { showTitle: true },
      render: (v: string) => (
        <Text
          style={{
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
            fontSize: 13,
          }}
          title={v}
        >
          {v}
        </Text>
      ),
    },
    {
      title: "송신일",
      dataIndex: "sent_at",
      width: 160,
      render: (v: string | null) => (
        <Text type={v ? undefined : "secondary"} style={{ fontSize: 12 }}>
          {formatDateTime(v)}
        </Text>
      ),
    },
    {
      title: "상태",
      dataIndex: "status",
      width: 100,
      render: (v: string) => (
        <Tag color={MESSAGE_STATUS_COLOR[v] ?? "default"}>{v}</Tag>
      ),
    },
    {
      title: "작업",
      key: "actions",
      width: 110,
      render: (_: unknown, record: MessageSearchItem) => (
        <Link to={`/distribution/sessions/${record.session_id}`}>
          <Button type="link" size="small">
            세션 보기
          </Button>
        </Link>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Card size="small">
        <Space size={12} wrap>
          <Input.Search
            placeholder="메시지 본문에서 검색 (예: '입금', '재고')"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onSearch={handleSearch}
            enterButton={
              <Button type="primary" icon={<SearchOutlined />}>
                검색
              </Button>
            }
            allowClear
            style={{ width: 480 }}
            maxLength={100}
            loading={loading}
          />
          <Text type="secondary" style={{ fontSize: 12 }}>
            • 대소문자 무관, content / edited_content 모두 매칭
          </Text>
        </Space>
      </Card>

      <Card
        title={
          hasSearched
            ? `검색 결과 (${results.length}건)`
            : "검색어를 입력하세요"
        }
        size="small"
      >
        <Table
          columns={columns}
          dataSource={results}
          rowKey="message_id"
          loading={loading}
          size="small"
          scroll={{ x: 1000 }}
          pagination={{ pageSize: 20, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description={
                  hasSearched
                    ? "검색 결과가 없습니다"
                    : "위 입력창에 키워드를 입력하고 엔터를 누르세요"
                }
              />
            ),
          }}
        />
      </Card>
    </Space>
  );
}
