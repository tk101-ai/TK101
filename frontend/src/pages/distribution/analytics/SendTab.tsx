import { useCallback, useEffect, useState } from "react";
import {
  Card,
  Col,
  Empty,
  Row,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from "antd";
import { WarningOutlined } from "@ant-design/icons";
import type { ColumnsType } from "antd/es/table";
import {
  getSendFailures,
  getSessionStatusCounts,
  type SendFailureItem,
} from "../../../api/distribution_analytics";
import { extractErrorDetail } from "../../../utils/errorUtils";
import { formatDateTime } from "./format";
import {
  SESSION_STATUS_COLOR,
  SESSION_STATUS_KEYS,
  SESSION_STATUS_LABEL,
} from "./constants";
import type { RangeFilter } from "./types";

const { Text } = Typography;

interface SendTabProps {
  filter: RangeFilter;
}

export function SendTab({ filter }: SendTabProps) {
  const [counts, setCounts] = useState<Record<string, number>>({});
  const [failures, setFailures] = useState<SendFailureItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [c, f] = await Promise.all([
        getSessionStatusCounts(filter.from, filter.to),
        getSendFailures(filter.from, filter.to),
      ]);
      setCounts(c);
      setFailures(f);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "송신 통계 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [filter.from, filter.to]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const failureColumns: ColumnsType<SendFailureItem> = [
    {
      title: "에러 코드",
      dataIndex: "error_code",
      width: 220,
      render: (v: string) => (
        <Tag color={v === "UNKNOWN" ? "default" : "red"}>
          <span style={{ fontFamily: "monospace" }}>{v}</span>
        </Tag>
      ),
    },
    {
      title: "발생 횟수",
      dataIndex: "count",
      width: 120,
      align: "right",
      render: (v: number) => (
        <Text strong style={{ fontVariantNumeric: "tabular-nums" }}>
          {v}
        </Text>
      ),
    },
    {
      title: "마지막 시도",
      dataIndex: "last_attempted_at",
      width: 180,
      render: (v: string) => (
        <Text type="secondary" style={{ fontSize: 12 }}>
          {formatDateTime(v)}
        </Text>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={[12, 12]}>
        {SESSION_STATUS_KEYS.map((key) => (
          <Col xs={12} sm={8} md={4} key={key}>
            <Card size="small" loading={loading}>
              <Statistic
                title={SESSION_STATUS_LABEL[key]}
                value={counts[key] ?? 0}
                valueStyle={{ color: SESSION_STATUS_COLOR[key], fontSize: 22 }}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Card
        title={
          <Space>
            <WarningOutlined style={{ color: "#cf1322" }} />
            <span>송신 실패 원인 분류</span>
          </Space>
        }
        size="small"
      >
        <Table
          columns={failureColumns}
          dataSource={failures}
          rowKey="error_code"
          loading={loading}
          size="small"
          pagination={{ pageSize: 20, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="해당 기간에 송신 실패 기록이 없습니다"
              />
            ),
          }}
        />
      </Card>
    </Space>
  );
}
