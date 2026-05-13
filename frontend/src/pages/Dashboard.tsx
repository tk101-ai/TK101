import { useAuth } from "../hooks/useAuth";
import FinanceDashboard from "./dashboards/FinanceDashboard";
import AdminDashboard from "./dashboards/AdminDashboard";
import Marketing1Dashboard from "./dashboards/Marketing1Dashboard";
import Marketing2Dashboard from "./dashboards/Marketing2Dashboard";
import NewBusinessDashboard from "./dashboards/NewBusinessDashboard";
import NewMediaDashboard from "./dashboards/NewMediaDashboard";
import DesignDashboard from "./dashboards/DesignDashboard";
import PlaceholderDashboard from "./dashboards/PlaceholderDashboard";
import { DEPARTMENTS, type DepartmentKey } from "../config/modules";

export default function Dashboard() {
  const { user } = useAuth();
  if (!user) return null;

  const dept = user.department as DepartmentKey;

  if (dept === "finance") return <FinanceDashboard />;
  if (dept === "admin") return <AdminDashboard />;
  if (dept === "marketing_1") return <Marketing1Dashboard />;
  if (dept === "marketing_2") return <Marketing2Dashboard />;
  if (dept === "new_business") return <NewBusinessDashboard />;
  if (dept === "new_media") return <NewMediaDashboard />;
  if (dept === "design") return <DesignDashboard />;

  // 알 수 없는 부서 fallback — PlaceholderDashboard로 안전하게 처리.
  return (
    <PlaceholderDashboard
      departmentLabel={DEPARTMENTS[dept] ?? user.department}
      widgets={[]}
    />
  );
}
