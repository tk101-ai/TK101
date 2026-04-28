import { Layout, Menu } from "antd";
import { LogoutOutlined } from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import type { User } from "../api/auth";
import { NAV_ITEMS, getDepartmentLabel } from "../config/modules";

const { Content, Sider } = Layout;

export default function AppLayout({ user, onLogout }: { user: User; onLogout: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = NAV_ITEMS
    .filter((item) => user.modules.includes(item.module))
    .map((item) => ({
      key: item.path,
      icon: item.icon,
      label: item.label,
    }));

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
            {user.name} ({getDepartmentLabel(user.department)})
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
