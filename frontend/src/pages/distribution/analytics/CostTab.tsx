import { useCallback, useEffect, useMemo, useState } from "react";
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
import type { ColumnsType } from "antd/es/table";
import {
  getCostByDay,
  getCostByPersona,
  type CostByDayItem,
  type CostByPersonaItem,
} from "../../../api/distribution_analytics";
import { extractErrorDetail } from "../../../utils/errorUtils";
import { formatCostUsd, formatDate, sumCostUsd } from "./format";
import type { RangeFilter } from "./types";

const { Text } = Typography;

interface CostTabProps {
  filter: RangeFilter;
}

export function CostTab({ filter }: CostTabProps) {
  const [byDay, setByDay] = useState<CostByDayItem[]>([]);
  const [byPersona, setByPersona] = useState<CostByPersonaItem[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchAll = useCallback(async () => {
    setLoading(true);
    try {
      const [day, persona] = await Promise.all([
        getCostByDay(filter.from, filter.to),
        getCostByPersona(filter.from, filter.to),
      ]);
      setByDay(day);
      setByPersona(persona);
    } catch (err: unknown) {
      message.error(extractErrorDetail(err, "비용 데이터 조회 실패"));
    } finally {
      setLoading(false);
    }
  }, [filter.from, filter.to]);

  useEffect(() => {
    void fetchAll();
  }, [fetchAll]);

  const totals = useMemo(() => {
    const totalCost = sumCostUsd(byDay);
    const totalSessions = byDay.reduce((a, r) => a + r.session_count, 0);
    return { totalCost, totalSessions };
  }, [byDay]);

  const dayColumns: ColumnsType<CostByDayItem> = [
    {
      title: "날짜",
      dataIndex: "date",
      width: 140,
      render: (v: string) => <Text strong>{formatDate(v)}</Text>,
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
    {
      title: "세션 수",
      dataIndex: "session_count",
      width: 100,
      align: "right",
      render: (v: number) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{v}</span>
      ),
    },
  ];

  const personaColumns: ColumnsType<CostByPersonaItem> = [
    {
      title: "페르소나",
      dataIndex: "account_label",
      width: 160,
      render: (v: string) => <Tag color="geekblue">{v}</Tag>,
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
    {
      title: "세션 수",
      dataIndex: "session_count",
      width: 100,
      align: "right",
      render: (v: number) => (
        <span style={{ fontVariantNumeric: "tabular-nums" }}>{v}</span>
      ),
    },
  ];

  return (
    <Space direction="vertical" size={16} style={{ width: "100%" }}>
      <Row gutter={16}>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="기간 총 비용"
              value={totals.totalCost}
              precision={4}
              prefix="$"
              valueStyle={{ color: "#cf1322" }}
            />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic title="기간 세션 수" value={totals.totalSessions} />
          </Card>
        </Col>
        <Col xs={24} md={8}>
          <Card>
            <Statistic
              title="세션당 평균"
              value={
                totals.totalSessions > 0
                  ? totals.totalCost / totals.totalSessions
                  : 0
              }
              precision={4}
              prefix="$"
            />
          </Card>
        </Col>
      </Row>

      <Card title="일별 비용" size="small">
        <Table
          columns={dayColumns}
          dataSource={byDay}
          rowKey="date"
          loading={loading}
          size="small"
          pagination={{ pageSize: 14, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="해당 기간에 비용 기록이 없습니다"
              />
            ),
          }}
        />
      </Card>

      <Card title="페르소나(발신자)별 비용" size="small">
        <Table
          columns={personaColumns}
          dataSource={byPersona}
          rowKey="persona_id"
          loading={loading}
          size="small"
          pagination={{ pageSize: 10, showSizeChanger: false }}
          locale={{
            emptyText: (
              <Empty
                image={Empty.PRESENTED_IMAGE_SIMPLE}
                description="해당 기간에 발신 페르소나가 없습니다"
              />
            ),
          }}
        />
      </Card>
    </Space>
  );
}
