import { ConfigProvider, Spin } from "antd";
import koKR from "antd/locale/ko_KR";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import AppLayout from "./components/AppLayout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Accounts from "./pages/Accounts";
import TaxInvoices from "./pages/TaxInvoices";
import Users from "./pages/Users";

function App() {
  const { user, loading, logout, checkAuth } = useAuth();

  if (loading) {
    return (
      <div style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "100vh" }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <ConfigProvider locale={koKR}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={user ? <Navigate to="/" /> : <Login onLogin={checkAuth} />} />
          {user ? (
            <Route element={<AppLayout user={user} onLogout={logout} />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/transactions" element={<Transactions />} />
              <Route path="/accounts" element={<Accounts />} />
              <Route path="/tax-invoices" element={<TaxInvoices />} />
              <Route path="/users" element={<Users />} />
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
