import { Button } from "antd";
import { ApartmentOutlined } from "@ant-design/icons";
import { useNavigate } from "react-router-dom";
import DepartmentBaseDashboard, {
  type UpcomingWidget,
} from "./DepartmentBaseDashboard";

const NEW_BUSINESS_UPCOMING: UpcomingWidget[] = [
  {
    title: "프로젝트 파이프라인",
    description: "진행 중 신사업 프로젝트 단계별 분포 (리드 → 협상 → 계약)",
  },
  {
    title: "제휴·파트너십",
    description: "협상 단계별 파트너십 현황 및 담당자",
  },
  {
    title: "분기 마일스톤",
    description: "이번 분기 목표 달성률과 다음 액션",
  },
];

export default function NewBusinessDashboard() {
  const navigate = useNavigate();
  return (
    <DepartmentBaseDashboard
      departmentLabel="신사업팀"
      upcoming={NEW_BUSINESS_UPCOMING}
      // 신사업팀 주력 모듈(distribution=신사업유통)로 바로 진입.
      extraQuickActions={
        <Button
          type="primary"
          ghost
          icon={<ApartmentOutlined />}
          onClick={() => navigate("/distribution/dashboard")}
        >
          신사업유통 대시보드
        </Button>
      }
    />
  );
}
