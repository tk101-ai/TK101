import DepartmentBaseDashboard, {
  type UpcomingWidget,
} from "./DepartmentBaseDashboard";

const NEW_MEDIA_UPCOMING: UpcomingWidget[] = [
  {
    title: "채널 구독·팔로워 추이",
    description: "유튜브/인스타/틱톡 채널별 주간 변화량",
  },
  {
    title: "콘텐츠 성과 Top",
    description: "최근 발행 콘텐츠 조회수/참여율 상위 5건",
  },
  {
    title: "업로드 캘린더",
    description: "이번 주 업로드 예정 콘텐츠 및 담당자",
  },
];

export default function NewMediaDashboard() {
  return (
    <DepartmentBaseDashboard
      departmentLabel="뉴미디어팀"
      upcoming={NEW_MEDIA_UPCOMING}
    />
  );
}
