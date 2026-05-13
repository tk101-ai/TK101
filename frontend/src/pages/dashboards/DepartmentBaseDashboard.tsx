import { Alert, Button, Card, Col, Row, Space, Spin, Statistic, Tag } from "antd";
import {
  ArrowRightOutlined,
  ClockCircleOutlined,
  CloudServerOutlined,
  EditOutlined,
  FileTextOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import dayjs from "dayjs";

import { getNasStatus, type NasStatus } from "../../api/nas";
import { listFormTemplates } from "../../api/forms";

/**
 * 부서별 대시보드의 베이스 컴포넌트.
 *
 * 마케팅2/신사업/뉴미디어/디자인 4개 부서가 현재 동일한 모듈 권한
 * (dashboard + nas_search + form_filler)을 공유하므로 공통 위젯을 베이스에 두고
 * 각 부서 대시보드는 헤더 라벨과 부서별 "준비 중" 위젯 슬롯만 주입한다.
 *
 * 향후 부서별로 전용 KPI가 늘어나면 `extraKpiCards` slot으로 확장한다.
 */

export interface UpcomingWidget {
  title: string;
  description: string;
}

export interface DepartmentBaseDashboardProps {
  departmentLabel: string;
  upcoming: UpcomingWidget[];
  /** 부서별 추가 KPI 카드(선택). KISS — 현재는 4개 부서 모두 미사용. */
  extraKpiCards?: React.ReactNode;
}

interface KpiState {
  nas: NasStatus | null;
  templateCount: number;
}

const INITIAL_KPI: KpiState = {
  nas: null,
  templateCount: 0,
};

export default function DepartmentBaseDashboard({
  departmentLabel,
  upcoming,
  extraKpiCards,
}: DepartmentBaseDashboardProps) {
  const navigate = useNavigate();
  const [kpi, setKpi] = useState<KpiState>(INITIAL_KPI);
  const [loading, setLoading] = useState<boolean>(true);

  const fetchKpi = useCallback(async () => {
    setLoading(true);
    try {
      // 둘 다 실패해도 placeholder UI가 노출되도록 settle.
      const [nasRes, tplRes] = await Promise.allSettled([
        getNasStatus(),
        listFormTemplates({}),
      ]);

      const next: KpiState = { ...INITIAL_KPI };
      if (nasRes.status === "fulfilled") next.nas = nasRes.value.data;
      if (tplRes.status === "fulfilled") next.templateCount = tplRes.value.length;
      setKpi(next);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // 마운트 시 1회 KPI fetch. 부서 대시보드는 새로고침 시점에만 갱신해도 충분.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchKpi();
  }, [fetchKpi]);

  const lastIndexedLabel = useMemo(() => {
    if (!kpi.nas?.last_indexed_at) return "기록 없음";
    return dayjs(kpi.nas.last_indexed_at).format("MM-DD HH:mm");
  }, [kpi.nas]);

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
          {`${departmentLabel} 대시보드`}
        </h2>

        {/* KPI Cards — 부서 공통 모듈 (NAS + FormFiller) */}
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} lg={6}>
            <Card
              hoverable
              style={{ borderLeft: "3px solid #13c2c2" }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="NAS 인덱싱 자료"
                value={kpi.nas?.indexed_files ?? 0}
                prefix={<CloudServerOutlined style={{ color: "#13c2c2" }} />}
                suffix="건"
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
            <Card
              hoverable
              style={{ borderLeft: "3px solid #2f54eb" }}
              styles={{ body: { padding: "20px 24px" } }}
            >
              <Statistic
                title="전체 자료 수"
                value={kpi.nas?.total_files ?? 0}
                prefix={<FileTextOutlined style={{ color: "#2f54eb" }} />}
                suffix="건"
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
                title="등록된 양식"
                value={kpi.templateCount}
                prefix={<EditOutlined style={{ color: "#fa8c16" }} />}
                suffix="개"
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} lg={6}>
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

        {extraKpiCards}

        {/* Quick Actions */}
        <Card
          title="빠른 액션"
          style={{ marginTop: 16 }}
          styles={{ body: { padding: "16px 20px" } }}
        >
          <Space size="middle" wrap>
            <Button
              type="primary"
              icon={<SearchOutlined />}
              onClick={() => navigate("/nas/search")}
            >
              NAS 자료 검색
            </Button>
            <Button
              icon={<EditOutlined />}
              onClick={() => navigate("/forms/new")}
            >
              문서 자동 작성
            </Button>
            <Button
              icon={<FileTextOutlined />}
              onClick={() => navigate("/forms/library")}
            >
              양식 라이브러리
            </Button>
          </Space>
        </Card>

        {/* 부서 전용 위젯 (준비 중) */}
        <div style={{ marginTop: 24 }}>
          <Alert
            type="info"
            showIcon
            message="부서 전용 위젯은 추후 부서 요구사항 수집 후 추가될 예정입니다."
            style={{ marginBottom: 16 }}
          />
          {upcoming.length > 0 && (
            <Row gutter={[16, 16]}>
              {upcoming.map((widget) => (
                <Col xs={24} sm={12} lg={8} key={widget.title}>
                  <Card
                    hoverable
                    style={{ borderLeft: "3px solid #fa8c16", height: "100%" }}
                    styles={{ body: { padding: "20px 24px" } }}
                    title={widget.title}
                    extra={<Tag color="orange">준비 중</Tag>}
                    actions={[
                      <span
                        key="request"
                        style={{ color: "rgba(0,0,0,0.45)", fontSize: 12 }}
                      >
                        요청 시 추가 <ArrowRightOutlined />
                      </span>,
                    ]}
                  >
                    <div
                      style={{
                        color: "rgba(0,0,0,0.55)",
                        fontSize: 13,
                        lineHeight: 1.6,
                      }}
                    >
                      {widget.description}
                    </div>
                  </Card>
                </Col>
              ))}
            </Row>
          )}
        </div>
      </div>
    </Spin>
  );
}
