import { ConfigProvider, Spin, theme as antdTheme } from "antd";
import koKR from "antd/locale/ko_KR";
import { useEffect, useState } from "react";
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
import ReviewTranslationPage from "./pages/marketing/ReviewTranslation";
import NasSearch from "./pages/nas/Search";
import FormUploadPage from "./pages/forms/FormUploadPage";
import FormReviewPage from "./pages/forms/FormReviewPage";
import FormLibraryPage from "./pages/forms/FormLibraryPage";
import JobNewPage from "./pages/forms/JobNewPage";
import JobMappingPage from "./pages/forms/JobMappingPage";
import TransactionImport from "./pages/finance/TransactionImport";
import MatchingWorkbook from "./pages/finance/MatchingWorkbook";
import UploadHistory from "./pages/finance/UploadHistory";
import CategoryPage from "./pages/settings/CategoryPage";
import CounterpartPage from "./pages/settings/CounterpartPage";
import PlaygroundPage from "./pages/playground/PlaygroundPage";
import UsagePage from "./pages/playground/UsagePage";
import DashboardPage from "./pages/distribution/DashboardPage";
import PersonasPage from "./pages/distribution/PersonasPage";
import DataUploadPage from "./pages/distribution/DataUploadPage";
import WeeklyDataPage from "./pages/distribution/WeeklyDataPage";
import ProductsPage from "./pages/distribution/ProductsPage";
import SessionsPage from "./pages/distribution/SessionsPage";
import SessionDetailPage from "./pages/distribution/SessionDetailPage";
import AnalyticsPage from "./pages/distribution/AnalyticsPage";
import SettlementPage from "./pages/distribution/SettlementPage";

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
          {user ? (
            <Route element={<AppLayout user={user} onLogout={logout} darkMode={darkMode} onToggleDark={() => setDarkMode((d) => !d)} />}>
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
                path="/finance/import"
                element={
                  <ProtectedRoute user={user} module="finance">
                    <TransactionImport />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/finance/matching"
                element={
                  <ProtectedRoute user={user} module="finance">
                    <MatchingWorkbook />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/finance/upload-history"
                element={
                  <ProtectedRoute user={user} module="finance">
                    <UploadHistory />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/settings/categories"
                element={
                  <ProtectedRoute user={user} module="finance">
                    <CategoryPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/settings/counterparts"
                element={
                  <ProtectedRoute user={user} module="finance">
                    <CounterpartPage />
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
                path="/marketing/review-translation"
                element={
                  <ProtectedRoute user={user} module="review_translation">
                    <ReviewTranslationPage />
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
              <Route
                path="/playground"
                element={
                  <ProtectedRoute user={user} module="playground">
                    <PlaygroundPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/playground/usage"
                element={
                  <ProtectedRoute user={user} module="playground_usage">
                    <UsagePage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/distribution/dashboard"
                element={
                  <ProtectedRoute user={user} module="distribution">
                    <DashboardPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/distribution/personas"
                element={
                  <ProtectedRoute user={user} module="distribution">
                    <PersonasPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/distribution/data/upload"
                element={
                  <ProtectedRoute user={user} module="distribution">
                    <DataUploadPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/distribution/data/weekly"
                element={
                  <ProtectedRoute user={user} module="distribution">
                    <WeeklyDataPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/distribution/data/products"
                element={
                  <ProtectedRoute user={user} module="distribution">
                    <ProductsPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/distribution/sessions"
                element={
                  <ProtectedRoute user={user} module="distribution">
                    <SessionsPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/distribution/sessions/:id"
                element={
                  <ProtectedRoute user={user} module="distribution">
                    <SessionDetailPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/distribution/analytics"
                element={
                  <ProtectedRoute user={user} module="distribution">
                    <AnalyticsPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/distribution/settlement"
                element={
                  <ProtectedRoute user={user} module="distribution">
                    <SettlementPage />
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
