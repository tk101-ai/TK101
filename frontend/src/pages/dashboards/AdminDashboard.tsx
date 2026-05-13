import { Card, Col, Row, Statistic, Button, Table, Tag, Space, message, Spin, Tabs } from "antd";
import {
  TeamOutlined,
  ApartmentOutlined,
  AppstoreOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  LinkOutlined,
  CloudServerOutlined,
  ClockCircleOutlined,
} from "@ant-design/icons";
import { useEffect, useState, useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import api from "../../api/client";
import { getNasStatus, type NasStatus } from "../../api/nas";
import { getDepartmentLabel, NAV_ITEMS } from "../../config/modules";
import FinanceDashboard from "./FinanceDashboard";
import Marketing1Dashboard from "./Marketing1Dashboard";
import Marketing2Dashboard from "./Marketing2Dashboard";
import NewBusinessDashboard from "./NewBusinessDashboard";
import NewMediaDashboard from "./NewMediaDashboard";
import DesignDashboard from "./DesignDashboard";

// 유효한 탭 키 집합 — URL 쿼리스트링 검증용.
const VALID_TAB_KEYS = [
  "admin",
  "finance",
  "marketing_1",
  "marketing_2",
  "new_business",
  "new_media",
  "design",
] as const;
type AdminTabKey = (typeof VALID_TAB_KEYS)[number];
const DEFAULT_TAB: AdminTabKey = "admin";

function isValidTabKey(key: string | null): key is AdminTabKey {
  return key !== null && (VALID_TAB_KEYS as readonly string[]).includes(key);
}

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

// 외부 시스템 URL은 nginx 리버스 프록시(/n8n) 경유를 표준으로 한다.
// 추후 직접 포트(:5678)를 외부에 노출하지 않도록 정합성 유지.
const EXTERNAL_LINKS: ExternalLink[] = [
  {
    title: "n8n 워크플로",
    description: "자동화 워크플로 관리 (관리자 전용 리버스 프록시)",
    url: "/n8n/",
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

// 기존 관리자 본문을 별도 컴포넌트로 추출.
// Tabs가 lazy 렌더하므로 "관리자" 탭이 활성일 때만 마운트되어 fetch 발생.
function AdminHomePanel() {
  const [deptStats, setDeptStats] = useState<DepartmentStat[]>([]);
  const [totalUsers, setTotalUsers] = useState(0);
  const [nasStatus, setNasStatus] = useState<NasStatus | null>(null);
  const [loading, setLoading] = useState(true);

  // 모듈 수: 백엔드에 /api/modules 가 없으므로 frontend NAV_ITEMS의 distinct module 개수로 산정.
  // (사이드바에 등록되지 않은 백엔드-only 모듈은 카운트에서 제외 — 사용자가 보는 모듈 기준.)
  const moduleCount = useMemo(() => {
    const set = new Set(NAV_ITEMS.map((i) => i.module));
    return set.size;
  }, []);

  const fetchStats = useCallback(async () => {
    setLoading(true);
    try {
      // 부서 통계와 NAS 상태를 병렬 fetch — 한 쪽 실패해도 다른 쪽은 노출되도록 settle 처리.
      const [usersRes, nasRes] = await Promise.allSettled([
        api.get<DepartmentStat[]>("/api/users/stats"),
        getNasStatus(),
      ]);

      if (usersRes.status === "fulfilled") {
        const data = usersRes.value.data ?? [];
        setDeptStats(data);
        setTotalUsers(data.reduce((sum, d) => sum + (d.count ?? 0), 0));
      } else {
        message.error("부서 통계를 불러오는데 실패했습니다.");
      }

      if (nasRes.status === "fulfilled") {
        setNasStatus(nasRes.value.data);
      }
      // NAS 실패는 에러 토스트 안 띄움 — 보조 정보라 조용히 fallback.
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // 마운트 시 관리자 통계 fetch (의도된 패턴).
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchStats();
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

  const nasIndexProgress = useMemo(() => {
    if (!nasStatus || nasStatus.total_files === 0) return 0;
    return Math.round((nasStatus.indexed_files / nasStatus.total_files) * 100);
  }, [nasStatus]);

  const lastIndexedLabel = useMemo(() => {
    if (!nasStatus?.last_indexed_at) return "기록 없음";
    return dayjs(nasStatus.last_indexed_at).format("MM-DD HH:mm");
  }, [nasStatus]);

  const systemHealthy = nasStatus?.mount_ok !== false;

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

        {/* Summary Cards (1행: 운영 KPI) */}
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
                title="활성 부서 수"
                value={deptStats.length}
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
                value={moduleCount}
                prefix={<AppstoreOutlined style={{ color: "#fa8c16" }} />}
                suffix="개"
              />
            </Card>
          </Col>

          <Col xs={24} sm={12} lg={6}>
            <Card
              hoverable
              style={{
                borderLeft: `3px solid ${systemHealthy ? "#52c41a" : "#cf1322"}`,
              }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="시스템 상태"
                value={systemHealthy ? "정상" : "NAS 점검 필요"}
                prefix={
                  systemHealthy ? (
                    <CheckCircleOutlined style={{ color: "#52c41a" }} />
                  ) : (
                    <CloseCircleOutlined style={{ color: "#cf1322" }} />
                  )
                }
                valueStyle={{
                  color: systemHealthy ? "#52c41a" : "#cf1322",
                  fontSize: 18,
                }}
              />
            </Card>
          </Col>
        </Row>

        {/* Summary Cards (2행: NAS 인덱싱 헬스) */}
        <Row gutter={[16, 16]} style={{ marginTop: 16 }}>
          <Col xs={24} sm={12} lg={8}>
            <Card
              hoverable
              style={{ borderLeft: "3px solid #13c2c2" }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="NAS 인덱싱 파일 수"
                value={nasStatus?.indexed_files ?? 0}
                prefix={<CloudServerOutlined style={{ color: "#13c2c2" }} />}
                suffix={`/ ${(nasStatus?.total_files ?? 0).toLocaleString("ko-KR")}건`}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <Card
              hoverable
              style={{ borderLeft: "3px solid #2f54eb" }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="NAS 인덱싱 진행률"
                value={nasIndexProgress}
                suffix="%"
                valueStyle={{ fontSize: 22, fontWeight: 700 }}
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={8}>
            <Card
              hoverable
              style={{ borderLeft: "3px solid #8c8c8c" }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="마지막 인덱싱"
                value={lastIndexedLabel}
                prefix={<ClockCircleOutlined style={{ color: "#8c8c8c" }} />}
                valueStyle={{ fontSize: 18 }}
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

// admin 사용자가 상단 Tabs로 각 부서 대시보드를 전환해서 볼 수 있도록 한다.
// 각 탭은 자체 데이터 fetch 책임이 있고, Antd Tabs는 기본적으로 활성 패널만 렌더하므로
// "관리자" 탭이 아닐 때는 admin 통계 호출이 발생하지 않는다.
export default function AdminDashboard() {
  const [searchParams, setSearchParams] = useSearchParams();
  const tabFromUrl = searchParams.get("tab");
  const activeKey: AdminTabKey = isValidTabKey(tabFromUrl) ? tabFromUrl : DEFAULT_TAB;

  const handleTabChange = useCallback(
    (key: string) => {
      // URL 쿼리스트링과 동기화 — 새로고침해도 같은 탭 유지.
      const next = new URLSearchParams(searchParams);
      if (key === DEFAULT_TAB) {
        next.delete("tab");
      } else {
        next.set("tab", key);
      }
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const items = useMemo(
    () => [
      { key: "admin", label: "관리자", children: <AdminHomePanel /> },
      { key: "finance", label: "재무팀", children: <FinanceDashboard /> },
      { key: "marketing_1", label: "마케팅 1팀", children: <Marketing1Dashboard /> },
      { key: "marketing_2", label: "마케팅 2팀", children: <Marketing2Dashboard /> },
      { key: "new_business", label: "신사업팀", children: <NewBusinessDashboard /> },
      { key: "new_media", label: "뉴미디어팀", children: <NewMediaDashboard /> },
      { key: "design", label: "디자인팀", children: <DesignDashboard /> },
    ],
    [],
  );

  return (
    <div style={{ padding: "0 4px" }}>
      <Tabs
        activeKey={activeKey}
        defaultActiveKey={DEFAULT_TAB}
        onChange={handleTabChange}
        items={items}
        size="large"
        // destroyInactiveTabPane: 비활성 탭 언마운트 → 다른 부서 대시보드의 fetch가 background에서 돌지 않도록.
        destroyInactiveTabPane
      />
    </div>
  );
}
