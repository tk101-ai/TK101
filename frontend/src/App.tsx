import { ConfigProvider, Spin } from "antd";
import koKR from "antd/locale/ko_KR";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import AppLayout from "./components/AppLayout";
import ProtectedRoute from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Transactions from "./pages/Transactions";
import Accounts from "./pages/Accounts";
import TaxInvoices from "./pages/TaxInvoices";
import Users from "./pages/Users";
import SnsAccounts from "./pages/marketing/SnsAccounts";
import SnsPosts from "./pages/marketing/SnsPosts";
import SnsWeeklySnapshots from "./pages/marketing/SnsWeeklySnapshots";
import SnsExcelImport from "./pages/marketing/SnsExcelImport";
import NasSearch from "./pages/nas/Search";
import FormUploadPage from "./pages/forms/FormUploadPage";
import FormReviewPage from "./pages/forms/FormReviewPage";
import FormLibraryPage from "./pages/forms/FormLibraryPage";
import JobNewPage from "./pages/forms/JobNewPage";
import JobMappingPage from "./pages/forms/JobMappingPage";

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
              <Route
                path="/transactions"
                element={
                  <ProtectedRoute user={user} module="finance">
                    <Transactions />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/accounts"
                element={
                  <ProtectedRoute user={user} module="finance">
                    <Accounts />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tax-invoices"
                element={
                  <ProtectedRoute user={user} module="finance">
                    <TaxInvoices />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/users"
                element={
                  <ProtectedRoute user={user} module="users">
                    <Users />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/sns/accounts"
                element={
                  <ProtectedRoute user={user} module="marketing_sns">
                    <SnsAccounts />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/sns/posts"
                element={
                  <ProtectedRoute user={user} module="marketing_sns">
                    <SnsPosts />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/sns/snapshots"
                element={
                  <ProtectedRoute user={user} module="marketing_sns">
                    <SnsWeeklySnapshots />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/sns/import"
                element={
                  <ProtectedRoute user={user} module="marketing_sns">
                    <SnsExcelImport />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/nas/search"
                element={
                  <ProtectedRoute user={user} module="nas_search">
                    <NasSearch />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/forms/new"
                element={
                  <ProtectedRoute user={user} module="form_filler">
                    <FormUploadPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/forms/library"
                element={
                  <ProtectedRoute user={user} module="form_filler">
                    <FormLibraryPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/forms/templates/:id/review"
                element={
                  <ProtectedRoute user={user} module="form_filler">
                    <FormReviewPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/forms/jobs/:id/sources"
                element={
                  <ProtectedRoute user={user} module="form_filler">
                    <JobNewPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/forms/jobs/:id/review"
                element={
                  <ProtectedRoute user={user} module="form_filler">
                    <JobMappingPage />
                  </ProtectedRoute>
                }
              />
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
