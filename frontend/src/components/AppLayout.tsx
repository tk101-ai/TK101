import { Layout, Menu } from "antd";
import { BankOutlined, DashboardOutlined, LogoutOutlined, SwapOutlined } from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import type { User } from "../api/auth";

const { Content, Sider } = Layout;

const menuItems = [
  { key: "/", icon: <DashboardOutlined />, label: "대시보드" },
  { key: "/transactions", icon: <SwapOutlined />, label: "거래내역" },
  { key: "/accounts", icon: <BankOutlined />, label: "계좌 관리" },
];

export default function AppLayout({ user, onLogout }: { user: User; onLogout: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider breakpoint="lg" collapsedWidth="60">
        <div style={{ color: "#fff", textAlign: "center", padding: "16px 0", fontWeight: 700, fontSize: 16 }}>
          TK101
        </div>
        <Menu
          theme="dark"
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
        <div style={{ position: "absolute", bottom: 16, width: "100%", textAlign: "center" }}>
          <div style={{ color: "rgba(255,255,255,0.6)", fontSize: 12, marginBottom: 8 }}>
            {user.name} ({user.department || "N/A"})
          </div>
          <LogoutOutlined
            style={{ color: "rgba(255,255,255,0.6)", fontSize: 18, cursor: "pointer" }}
            onClick={onLogout}
          />
        </div>
      </Sider>
      <Layout>
        <Content style={{ margin: 24, padding: 24, background: "#fff", borderRadius: 8 }}>
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
