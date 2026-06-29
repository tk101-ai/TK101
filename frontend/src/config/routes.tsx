import type { ReactElement } from "react";
import Dashboard from "../pages/Dashboard";
import Transactions from "../pages/Transactions";
import Accounts from "../pages/Accounts";
import TaxInvoices from "../pages/TaxInvoices";
import Users from "../pages/Users";
import SnsAccounts from "../pages/marketing/SnsAccounts";
import SnsWeeklySnapshots from "../pages/marketing/SnsWeeklySnapshots";
import SnsContentStatus from "../pages/marketing/SnsContentStatus";
import SnsExcelImport from "../pages/marketing/SnsExcelImport";
import SeoulSns from "../pages/marketing/SeoulSns";
import ReviewTranslationPage from "../pages/marketing/ReviewTranslation";
import Marketing1Dashboard from "../pages/dashboards/Marketing1Dashboard";
import NasSearch from "../pages/nas/Search";
import FormUploadPage from "../pages/forms/FormUploadPage";
import FormReviewPage from "../pages/forms/FormReviewPage";
import FormLibraryPage from "../pages/forms/FormLibraryPage";
import JobNewPage from "../pages/forms/JobNewPage";
import JobMappingPage from "../pages/forms/JobMappingPage";
import DocGenPage from "../pages/forms/DocGenPage";
import PromptLibraryPage from "../pages/forms/PromptLibraryPage";
import DongaPharmaWorkspace from "../pages/workspaces/DongaPharmaWorkspace";
import HyundaiWorkspace from "../pages/workspaces/HyundaiWorkspace";
import DocumentsUsagePage from "../pages/documents/DocumentsUsagePage";
import TransactionImport from "../pages/finance/TransactionImport";
import MatchingWorkbook from "../pages/finance/MatchingWorkbook";
import UploadHistory from "../pages/finance/UploadHistory";
import CategoryPage from "../pages/settings/CategoryPage";
import CounterpartPage from "../pages/settings/CounterpartPage";
import PlaygroundPage from "../pages/playground/PlaygroundPage";
import ContentLibraryPage from "../pages/playground/ContentLibraryPage";
import UsagePage from "../pages/playground/UsagePage";
import AdminSessionsPage from "../pages/playground/AdminSessionsPage";
import LogsPage from "../pages/playground/LogsPage";
import DashboardPage from "../pages/distribution/DashboardPage";
import PersonasPage from "../pages/distribution/PersonasPage";
import DataUploadPage from "../pages/distribution/DataUploadPage";
import WeeklyDataPage from "../pages/distribution/WeeklyDataPage";
import ProductsPage from "../pages/distribution/ProductsPage";
import SessionsPage from "../pages/distribution/SessionsPage";
import SessionDetailPage from "../pages/distribution/SessionDetailPage";
import AnalyticsPage from "../pages/distribution/AnalyticsPage";
import SettlementPage from "../pages/distribution/SettlementPage";
import CustomsPage from "../pages/distribution/CustomsPage";

/**
 * 보호 라우트 정의 — App.tsx 가 AppLayout 하위에서 .map() 으로 렌더한다.
 * `module` 없는 항목(예: "/")은 ProtectedRoute 로 감싸지 않고 그대로 노출.
 * `role` 이 있으면 ProtectedRoute 의 role 게이트를 추가로 적용.
 *
 * NAV_ITEMS(modules.tsx)와 이중으로 관리하지 않도록, 라우트 목록은 여기 한곳에서만 정의.
 */
export interface AppRoute {
  path: string;
  element: ReactElement;
  /** ProtectedRoute module 키. 미지정 시 가드 없이 노출. */
  module?: string;
  /** ProtectedRoute role 게이트(현재 "admin" 만 사용). */
  role?: "admin";
}

export const APP_ROUTES: AppRoute[] = [
  { path: "/", element: <Dashboard /> },
  { path: "/transactions", element: <Transactions />, module: "finance" },
  { path: "/accounts", element: <Accounts />, module: "finance" },
  { path: "/tax-invoices", element: <TaxInvoices />, module: "finance" },
  { path: "/finance/import", element: <TransactionImport />, module: "finance" },
  { path: "/finance/matching", element: <MatchingWorkbook />, module: "finance" },
  { path: "/finance/upload-history", element: <UploadHistory />, module: "finance" },
  { path: "/settings/categories", element: <CategoryPage />, module: "finance" },
  { path: "/settings/counterparts", element: <CounterpartPage />, module: "finance" },
  { path: "/users", element: <Users />, module: "users", role: "admin" },
  { path: "/sns/accounts", element: <SnsAccounts />, module: "marketing_sns" },
  { path: "/sns/snapshots", element: <SnsWeeklySnapshots />, module: "marketing_sns" },
  { path: "/sns/content-status", element: <SnsContentStatus />, module: "marketing_sns" },
  { path: "/sns/seoul", element: <SeoulSns />, module: "marketing_sns" },
  { path: "/sns/import", element: <SnsExcelImport />, module: "marketing_sns" },
  { path: "/marketing/dashboard", element: <Marketing1Dashboard />, module: "marketing_sns" },
  { path: "/marketing/review-translation", element: <ReviewTranslationPage />, module: "review_translation" },
  { path: "/nas/search", element: <NasSearch />, module: "nas_search" },
  { path: "/forms/new", element: <FormUploadPage />, module: "form_filler" },
  { path: "/forms/library", element: <FormLibraryPage />, module: "form_filler" },
  { path: "/forms/generate", element: <DocGenPage />, module: "form_filler" },
  { path: "/forms/prompts", element: <PromptLibraryPage />, module: "form_filler" },
  { path: "/workspaces/donga", element: <DongaPharmaWorkspace />, module: "test_workspace" },
  { path: "/workspaces/hyundai", element: <HyundaiWorkspace />, module: "test_workspace" },
  { path: "/forms/templates/:id/review", element: <FormReviewPage />, module: "form_filler" },
  { path: "/forms/jobs/:id/sources", element: <JobNewPage />, module: "form_filler" },
  { path: "/forms/jobs/:id/review", element: <JobMappingPage />, module: "form_filler" },
  { path: "/documents/usage", element: <DocumentsUsagePage />, module: "documents_admin_usage" },
  { path: "/playground", element: <PlaygroundPage />, module: "playground" },
  { path: "/playground/library", element: <ContentLibraryPage />, module: "playground" },
  { path: "/playground/usage", element: <UsagePage />, module: "playground_usage" },
  { path: "/playground/admin/sessions", element: <AdminSessionsPage />, module: "playground_admin_sessions" },
  { path: "/playground/admin/logs", element: <LogsPage />, module: "playground_logs" },
  { path: "/distribution/dashboard", element: <DashboardPage />, module: "distribution" },
  { path: "/distribution/personas", element: <PersonasPage />, module: "distribution" },
  { path: "/distribution/data/upload", element: <DataUploadPage />, module: "distribution" },
  { path: "/distribution/data/weekly", element: <WeeklyDataPage />, module: "distribution" },
  { path: "/distribution/data/products", element: <ProductsPage />, module: "distribution" },
  { path: "/distribution/sessions", element: <SessionsPage />, module: "distribution" },
  { path: "/distribution/sessions/:id", element: <SessionDetailPage />, module: "distribution" },
  { path: "/distribution/analytics", element: <AnalyticsPage />, module: "distribution" },
  { path: "/distribution/settlement", element: <SettlementPage />, module: "distribution" },
  { path: "/distribution/customs", element: <CustomsPage />, module: "distribution" },
];
