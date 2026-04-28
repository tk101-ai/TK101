import { useAuth } from "../hooks/useAuth";
import FinanceDashboard from "./dashboards/FinanceDashboard";
import AdminDashboard from "./dashboards/AdminDashboard";
import PlaceholderDashboard from "./dashboards/PlaceholderDashboard";
import { DEPARTMENTS, type DepartmentKey } from "../config/modules";

const PLACEHOLDER_WIDGETS: Record<string, { title: string; description: string }[]> = {
  marketing_1: [
    { title: "캠페인 성과", description: "진행 중 캠페인의 핵심 KPI 요약" },
    { title: "광고 지표", description: "채널별 노출/클릭/전환 통계" },
    { title: "콘텐츠 일정", description: "이번 주/이달 발행 예정 캘린더" },
  ],
  marketing_2: [
    { title: "캠페인 성과", description: "진행 중 캠페인의 핵심 KPI 요약" },
    { title: "광고 지표", description: "채널별 노출/클릭/전환 통계" },
    { title: "콘텐츠 일정", description: "이번 주/이달 발행 예정 캘린더" },
  ],
  new_business: [
    { title: "프로젝트 현황", description: "진행 중 신사업 프로젝트 단계별 분포" },
    { title: "제휴/파트너십", description: "협상 단계별 파이프라인" },
    { title: "이번 분기 마일스톤", description: "분기 목표 달성률" },
  ],
  new_media: [
    { title: "채널 통계", description: "유튜브/인스타/틱톡 구독·팔로워 추이" },
    { title: "콘텐츠 성과", description: "최근 콘텐츠 조회수/참여율 Top 5" },
    { title: "발행 캘린더", description: "이번 주 업로드 예정 콘텐츠" },
  ],
  design: [
    { title: "작업 큐", description: "부서별 디자인 요청 진행 현황" },
    { title: "리뷰 대기", description: "검수가 필요한 시안 목록" },
    { title: "납기 임박", description: "마감 3일 이내 작업" },
  ],
};

export default function Dashboard() {
  const { user } = useAuth();
  if (!user) return null;

  const dept = user.department as DepartmentKey;

  if (dept === "finance") return <FinanceDashboard />;
  if (dept === "admin") return <AdminDashboard />;

  return (
    <PlaceholderDashboard
      departmentLabel={DEPARTMENTS[dept] ?? user.department}
      widgets={PLACEHOLDER_WIDGETS[dept] ?? []}
    />
  );
}
