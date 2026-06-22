import { ConfigProvider, Spin, theme as antdTheme } from "antd";
import koKR from "antd/locale/ko_KR";
import { useEffect, useState } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import AppLayout from "./components/AppLayout";
import ProtectedRoute from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Register from "./pages/Register";
import { APP_ROUTES } from "./config/routes";

const DARK_MODE_KEY = "tk101_dark_mode";

function App() {
  const { user, loading, logout, checkAuth } = useAuth();
  const [darkMode, setDarkMode] = useState<boolean>(
    () => localStorage.getItem(DARK_MODE_KEY) === "true",
  );

  useEffect(() => {
    localStorage.setItem(DARK_MODE_KEY, String(darkMode));
    // 브라우저 native scrollbar/색 동기화.
    document.documentElement.style.colorScheme = darkMode ? "dark" : "light";
    document.body.style.background = darkMode ? "#000" : "#f5f5f5";
  }, [darkMode]);

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh" }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <ConfigProvider
      locale={koKR}
      theme={{
        algorithm: darkMode ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
      }}
    >
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={user ? <Navigate to="/" /> : <Login onLogin={checkAuth} />} />
          <Route path="/register" element={user ? <Navigate to="/" /> : <Register />} />
          {user ? (
            <Route element={<AppLayout user={user} onLogout={logout} darkMode={darkMode} onToggleDark={() => setDarkMode((d) => !d)} />}>
              {APP_ROUTES.map(({ path, element, module, role }) => (
                <Route
                  key={path}
                  path={path}
                  element={
                    module ? (
                      <ProtectedRoute user={user} module={module} role={role}>
                        {element}
                      </ProtectedRoute>
                    ) : (
                      element
                    )
                  }
                />
              ))}
            </Route>
          ) : (
            <Route path="*" element={<Navigate to="/login" />} />
          )}
        </Routes>
      </BrowserRouter>
    </ConfigProvider>
  );
}

export default App;
