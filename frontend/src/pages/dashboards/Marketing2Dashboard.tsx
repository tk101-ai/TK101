import DepartmentBaseDashboard, {
  type UpcomingWidget,
} from "./DepartmentBaseDashboard";

const MARKETING_2_UPCOMING: UpcomingWidget[] = [
  {
    title: "캠페인 운영 현황",
    description: "진행 중 캠페인 단계별 분포와 핵심 KPI 요약",
  },
  {
    title: "광고 채널 지표",
    description: "채널별 노출/클릭/전환 추이 (마케팅2팀 담당 채널 한정)",
  },
  {
    title: "콘텐츠 발행 일정",
    description: "이번 주/이달 발행 예정 콘텐츠 캘린더",
  },
];

export default function Marketing2Dashboard() {
  return (
    <DepartmentBaseDashboard
      departmentLabel="마케팅2팀"
      upcoming={MARKETING_2_UPCOMING}
    />
  );
}
