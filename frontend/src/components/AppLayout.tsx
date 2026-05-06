import { Layout, Menu } from "antd";
import { LogoutOutlined } from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import type { User } from "../api/auth";
import { buildSidebarMenuItems, getDepartmentLabel } from "../config/modules";

const { Content, Sider } = Layout;

export default function AppLayout({ user, onLogout }: { user: User; onLogout: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();

  const menuItems = buildSidebarMenuItems(user.modules);

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
          onClick={({ key }) => {
            // group 헤더 키(`group-finance` 등)는 라우트가 없으므로 무시.
            if (typeof key === "string" && key.startsWith("group-")) return;
            navigate(key);
          }}
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
