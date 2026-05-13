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
      <Sider
        breakpoint="lg"
        collapsedWidth="60"
        style={{
          height: "100vh",
          position: "sticky",
          top: 0,
          left: 0,
          overflow: "hidden",
        }}
      >
        {/*
          Ant Design Sider wraps these children in `.ant-layout-sider-children`
          (height: 100%). We use a flex column wrapper inside so the menu area
          scrolls independently and the logout footer stays pinned at the bottom.
        */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            height: "100%",
          }}
        >
          <div
            style={{
              color: "#fff",
              textAlign: "center",
              padding: "16px 0",
              fontWeight: 700,
              fontSize: 16,
              flexShrink: 0,
            }}
          >
            TK101
          </div>
          <div style={{ flex: 1, overflowY: "auto", overflowX: "hidden", minHeight: 0 }}>
            <Menu
              theme="dark"
              mode="inline"
              selectedKeys={[location.pathname]}
              items={menuItems}
              style={{ borderRight: 0 }}
              onClick={({ key }) => {
                // group 헤더 키(`group-finance` 등)는 라우트가 없으므로 무시.
                if (typeof key === "string" && key.startsWith("group-")) return;
                navigate(key);
              }}
            />
          </div>
          <div
            style={{
              flexShrink: 0,
              padding: "12px 0 16px",
              textAlign: "center",
              borderTop: "1px solid rgba(255,255,255,0.08)",
            }}
          >
            <div style={{ color: "rgba(255,255,255,0.6)", fontSize: 12, marginBottom: 8 }}>
              {user.name} ({getDepartmentLabel(user.department)})
            </div>
            <LogoutOutlined
              style={{ color: "rgba(255,255,255,0.6)", fontSize: 18, cursor: "pointer" }}
              onClick={onLogout}
            />
          </div>
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
