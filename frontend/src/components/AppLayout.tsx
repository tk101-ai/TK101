import { Layout, Menu, Space, theme, Tooltip } from "antd";
import {
  BulbFilled,
  BulbOutlined,
  LogoutOutlined,
} from "@ant-design/icons";
import { Outlet, useLocation, useNavigate } from "react-router-dom";
import type { User } from "../api/auth";
import { buildSidebarMenuItems, getDepartmentLabel } from "../config/modules";

const { Content, Sider } = Layout;

interface AppLayoutProps {
  user: User;
  onLogout: () => void;
  /** 라이트/다크 토글. 사이드바 footer 의 전구 아이콘이 호출. */
  darkMode: boolean;
  onToggleDark: () => void;
}

export default function AppLayout({
  user,
  onLogout,
  darkMode,
  onToggleDark,
}: AppLayoutProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { token } = theme.useToken();

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
        {/* Sider 안 flex column. 메뉴는 스크롤, footer 는 하단 고정. */}
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
              letterSpacing: "0.05em",
            }}
          >
            TK101
          </div>
          <div
            className="tk-sidebar-scroll"
            style={{ flex: 1, overflowY: "auto", overflowX: "hidden", minHeight: 0 }}
          >
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
            <div
              style={{
                color: "rgba(255,255,255,0.6)",
                fontSize: 12,
                marginBottom: 8,
              }}
            >
              {user.name} ({getDepartmentLabel(user.department)})
            </div>
            <Space size={16}>
              <Tooltip title={darkMode ? "라이트 모드" : "다크 모드"} placement="top">
                {darkMode ? (
                  <BulbFilled
                    style={{
                      color: "rgba(255,200,80,0.9)",
                      fontSize: 18,
                      cursor: "pointer",
                    }}
                    onClick={onToggleDark}
                  />
                ) : (
                  <BulbOutlined
                    style={{
                      color: "rgba(255,255,255,0.6)",
                      fontSize: 18,
                      cursor: "pointer",
                    }}
                    onClick={onToggleDark}
                  />
                )}
              </Tooltip>
              <Tooltip title="로그아웃" placement="top">
                <LogoutOutlined
                  style={{
                    color: "rgba(255,255,255,0.6)",
                    fontSize: 18,
                    cursor: "pointer",
                  }}
                  onClick={onLogout}
                />
              </Tooltip>
            </Space>
          </div>
        </div>
      </Sider>
      <Layout style={{ background: token.colorBgLayout }}>
        <Content
          style={{
            margin: 24,
            padding: 24,
            background: token.colorBgContainer,
            borderRadius: token.borderRadiusLG,
            boxShadow: darkMode
              ? "0 1px 3px rgba(0,0,0,0.4)"
              : "0 1px 2px rgba(0,0,0,0.04)",
          }}
        >
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
