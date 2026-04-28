import { Card, Col, Row, Statistic, Button, Table, Tag, Space, message, Spin } from "antd";
import {
  TeamOutlined,
  ApartmentOutlined,
  AppstoreOutlined,
  CheckCircleOutlined,
  LinkOutlined,
} from "@ant-design/icons";
import { useEffect, useState, useCallback } from "react";
import type { ColumnsType } from "antd/es/table";
import api from "../../api/client";
import { getDepartmentLabel } from "../../config/modules";

interface DepartmentStat {
  department: string;
  count: number;
}

interface ExternalLink {
  title: string;
  description: string;
  url: string;
  color: string;
}

const FIXED_DEPARTMENT_COUNT = 7;
const FIXED_MODULE_COUNT = 3;

const EXTERNAL_LINKS: ExternalLink[] = [
  {
    title: "n8n 워크플로",
    description: "자동화 워크플로 관리",
    url: "http://43.155.202.112:5678",
    color: "#ea4b71",
  },
  {
    title: "Open WebUI",
    description: "AI 챗봇 인터페이스",
    url: "http://43.155.202.112:3000",
    color: "#1677ff",
  },
  {
    title: "Langfuse 관측성",
    description: "LLM 호출 트레이싱",
    url: "http://43.155.202.112:3001",
    color: "#722ed1",
  },
];

export default function AdminDashboard() {
  const [deptStats, setDeptStats] = useState<DepartmentStat[]>([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [loading, setLoading] = useState(true);

  const fetchStats = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get<DepartmentStat[]>("/api/users/stats");
      const data = res.data ?? [];
      setDeptStats(data);
      setTotalUsers(data.reduce((sum, d) => sum + (d.count ?? 0), 0));
    } catch {
      message.error("관리자 통계를 불러오는데 실패했습니다.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  const deptColumns: ColumnsType<DepartmentStat> = [
    {
      title: "부서",
      dataIndex: "department",
      key: "department",
      render: (val: string) => (
        <span style={{ fontWeight: 600 }}>{getDepartmentLabel(val)}</span>
      ),
    },
    {
      title: "인원",
      dataIndex: "count",
      key: "count",
      align: "right",
      width: 120,
      render: (val: number) => (
        <Tag color="blue" style={{ margin: 0, fontVariantNumeric: "tabular-nums" }}>
          {val}명
        </Tag>
      ),
    },
  ];

  return (
    <Spin spinning={loading} size="large">
      <div style={{ maxWidth: 1200, margin: "0 auto" }}>
        {/* Header */}
        <h2
          style={{
            marginBottom: 28,
            fontSize: 22,
            fontWeight: 700,
            letterSpacing: "-0.02em",
          }}
        >
          관리자 대시보드
        </h2>

        {/* Summary Cards */}
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={6}>
            <Card
              hoverable
              style={{ borderLeft: "3px solid #1677ff" }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="총 사용자 수 (활성)"
                value={totalUsers}
                prefix={<TeamOutlined style={{ color: "#1677ff" }} />}
                suffix="명"
              />
            </Card>
          </Col>

          <Col xs={24} sm={12} lg={6}>
            <Card
              hoverable
              style={{ borderLeft: "3px solid #722ed1" }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="총 부서 수"
                value={FIXED_DEPARTMENT_COUNT}
                prefix={<ApartmentOutlined style={{ color: "#722ed1" }} />}
                suffix="개"
              />
            </Card>
          </Col>

          <Col xs={24} sm={12} lg={6}>
            <Card
              hoverable
              style={{ borderLeft: "3px solid #fa8c16" }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="등록된 모듈 수"
                value={FIXED_MODULE_COUNT}
                prefix={<AppstoreOutlined style={{ color: "#fa8c16" }} />}
                suffix="개"
              />
            </Card>
          </Col>

          <Col xs={24} sm={12} lg={6}>
            <Card
              hoverable
              style={{ borderLeft: "3px solid #52c41a" }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="시스템 상태"
                value="정상"
                prefix={<CheckCircleOutlined style={{ color: "#52c41a" }} />}
                valueStyle={{ color: "#52c41a" }}
              />
            </Card>
          </Col>
        </Row>

        {/* Department breakdown */}
        <Card title="부서별 인원" style={{ marginTop: 16 }}>
          <Table<DepartmentStat>
            columns={deptColumns}
            dataSource={deptStats}
            rowKey="department"
            pagination={false}
            size="middle"
            locale={{ emptyText: "부서별 인원 데이터가 없습니다." }}
          />
        </Card>

        {/* External system links */}
        <h3
          style={{
            marginTop: 32,
            marginBottom: 16,
            fontSize: 16,
            fontWeight: 700,
            letterSpacing: "-0.01em",
          }}
        >
          외부 시스템 바로가기
        </h3>
        <Row gutter={[16, 16]}>
          {EXTERNAL_LINKS.map((link) => (
            <Col xs={24} sm={12} lg={8} key={link.url}>
              <Card
                hoverable
                style={{ borderLeft: `3px solid ${link.color}`, height: "100%" }}
                styles={{ body: { padding: "20px 24px" } }}
              >
                <Space direction="vertical" size="middle" style={{ width: "100%" }}>
                  <div>
                    <div
                      style={{
                        fontSize: 16,
                        fontWeight: 700,
                        color: link.color,
                        marginBottom: 4,
                      }}
                    >
                      {link.title}
                    </div>
                    <div style={{ color: "rgba(0,0,0,0.55)", fontSize: 13 }}>
                      {link.description}
                    </div>
                  </div>
                  <Button
                    type="primary"
                    icon={<LinkOutlined />}
                    block
                    onClick={() => window.open(link.url, "_blank", "noopener,noreferrer")}
                    style={{
                      height: 40,
                      fontWeight: 600,
                      background: link.color,
                      border: "none",
                    }}
                  >
                    바로 열기
                  </Button>
                </Space>
              </Card>
            </Col>
          ))}
        </Row>
      </div>
    </Spin>
  );
}
