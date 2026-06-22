import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Card,
  Col,
  Empty,
  Row,
  Space,
  Statistic,
  Table,
  Typography,
  message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import {
  getCostByDay,
  type CostByDayItem,
} from "../../../api/distribution_analytics";
import { extractErrorDetail } from "../../../utils/errorUtils";
import { formatCostUsd, formatDate } from "./format";
import type { RangeFilter } from "./types";

const { Text } = Typography;

interface SessionTrendTabProps {
  filter: RangeFilter;
}

export function SessionTrendTab({ filter }: SessionTrendTabProps) {
  const [byDay, setByDay] = useState<CostByDayItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const day = await getCostByDay(filter.from, filter.to);
      setByDay(day);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "세션 추이 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [filter.from, filter.to]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const totalSessions = useMemo(
    () => byDay.reduce((a, r) => a + r.session_count, 0),
    [byDay],
  );
  const peakDay = useMemo(() => {
    let peak: CostByDayItem | null = null;
    for (const row of byDay) {
      if (!peak || row.session_count > peak.session_count) peak = row;
    }
    return peak;
  }, [byDay]);

  const columns: ColumnsType<CostByDayItem> = [
    {
      title: "날짜",
      dataIndex: "date",
      width: 140,
      render: (v: string) => <Text strong>{formatDate(v)}</Text>,
    },
    {
      title: "세션 수",
      dataIndex: "session_count",
      width: 120,
      align: "right",
      render: (v: number) => (
        <Text
          strong
          style={{ fontVariantNumeric: "tabular-nums", color: "#1677ff" }}
        >
          {v}
        </Text>
      ),
    },
    {
      title: "비용 (USD)",
      dataIndex: "total_cost_usd",
      width: 160,
      align: "right",
      render: (v: string) => (
        <span style={{ fontFamily: "monospace", fontSize: 13 }}>
          {formatCostUsd(v)}
        </span>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="기간 총 세션" value={totalSessions} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="피크 일자"
              value={peakDay ? formatDate(peakDay.date) : "—"}
              valueStyle={{ fontSize: 18 }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="피크 일자 세션 수"
              value={peakDay?.session_count ?? 0}
              valueStyle={{ color: "#1677ff" }}
            />
          </Card>
        </Col>
      </Row>

      <Card title="일별 세션 생성 추이" size="small">
        <Table
          columns={columns}
          dataSource={byDay}
          rowKey="date"
          loading={loading}
          size="small"
          pagination={{ pageSize: 14, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="해당 기간에 세션 기록이 없습니다"
              />
            ),
          }}
        />
      </Card>
    </Space>
  );
}
