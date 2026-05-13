import DepartmentBaseDashboard, {
  type UpcomingWidget,
} from "./DepartmentBaseDashboard";

const DESIGN_UPCOMING: UpcomingWidget[] = [
  {
    title: "디자인 작업 큐",
    description: "부서별 디자인 요청 진행 단계 분포",
  },
  {
    title: "검수 대기 시안",
    description: "리뷰가 필요한 시안 목록 (담당자별)",
  },
  {
    title: "납기 임박 작업",
    description: "마감 3일 이내 작업 — 우선순위 정렬",
  },
];

export default function DesignDashboard() {
  return (
    <DepartmentBaseDashboard
      departmentLabel="디자인팀"
      upcoming={DESIGN_UPCOMING}
    />
  );
}
