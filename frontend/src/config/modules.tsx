import {
  ApartmentOutlined,
  AuditOutlined,
  BankOutlined,
  BarChartOutlined,
  BulbOutlined,
  CalculatorOutlined,
  CheckSquareOutlined,
  CloudUploadOutlined,
  ContactsOutlined,
  DashboardOutlined,
  EditOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  GlobalOutlined,
  GoldOutlined,
  HistoryOutlined,
  ImportOutlined,
  LineChartOutlined,
  LinkOutlined,
  MedicineBoxOutlined,
  PictureOutlined,
  RiseOutlined,
  RobotOutlined,
  SearchOutlined,
  SendOutlined,
  ShareAltOutlined,
  ShopOutlined,
  SwapOutlined,
  TableOutlined,
  TeamOutlined,
  TranslationOutlined,
} from "@ant-design/icons";
import type { MenuProps } from "antd";
import type { ReactNode } from "react";

export const DEPARTMENTS = {
  marketing_1: "마케팅1팀",
  marketing_2: "마케팅2팀",
  new_business: "신사업팀",
  finance: "재무팀",
  new_media: "뉴미디어팀",
  design: "디자인팀",
  admin: "관리자",
} as const;

export type DepartmentKey = keyof typeof DEPARTMENTS;

export const DEPARTMENT_OPTIONS = Object.entries(DEPARTMENTS).map(([value, label]) => ({ value, label }));

export const ROLES = {
  admin: "관리자",
  member: "일반",
} as const;

export type RoleKey = keyof typeof ROLES;

export const ROLE_OPTIONS = Object.entries(ROLES).map(([value, label]) => ({ value, label }));

export const ROLE_TAG_COLOR: Record<RoleKey, string> = {
  admin: "red",
  member: "default",
};

// 사이드바 카테고리. label=null이면 그룹 헤더 없이 최상단에 평평하게 노출.
// 부서 카테고리 키(finance/marketing_1/...)는 DEPARTMENTS 키와 의도적으로 일치 — 추후 부서 추가 시 양쪽 같이 등록.
type NavCategoryDef = { label: string | null; order: number };

export const NAV_CATEGORIES = {
  common: { label: null, order: 0 },
  form_work: { label: "문서 작업", order: 5 },
  finance: { label: "재무팀", order: 10 },
  marketing_1: { label: "마케팅1팀", order: 20 },
  marketing_2: { label: "마케팅2팀", order: 30 },
  new_business: { label: "신사업팀", order: 40 },
  new_media: { label: "뉴미디어팀", order: 50 },
  design: { label: "디자인팀", order: 60 },
  test_workspace: { label: "테스트", order: 80 },
  settings: { label: "설정", order: 90 },
  system: { label: "시스템", order: 99 },
} as const satisfies Record<string, NavCategoryDef>;

export type NavCategoryKey = keyof typeof NAV_CATEGORIES;

export interface NavItem {
  key: string;
  path: string;
  label: string;
  icon: ReactNode;
  module: string;
  category: NavCategoryKey;
}

export const NAV_ITEMS: NavItem[] = [
  { key: "dashboard", path: "/", label: "대시보드", icon: <DashboardOutlined />, module: "dashboard", category: "common" },
  { key: "nas-search", path: "/nas/search", label: "자료 검색", icon: <SearchOutlined />, module: "nas_search", category: "common" },
  { key: "forms-generate", path: "/forms/generate", label: "새 문서 작성", icon: <RobotOutlined />, module: "form_filler", category: "form_work" },
  { key: "forms-new", path: "/forms/new", label: "양식 채우기", icon: <EditOutlined />, module: "form_filler", category: "form_work" },
  { key: "forms-library", path: "/forms/library", label: "양식 라이브러리", icon: <FileTextOutlined />, module: "form_filler", category: "form_work" },
  { key: "forms-prompts", path: "/forms/prompts", label: "디자인 라이브러리", icon: <BulbOutlined />, module: "form_filler", category: "form_work" },
  // admin 전용 토큰/비용 패널. module=documents_admin_usage 는 admin 만 자동 부여(registry.ALL_MODULES).
  { key: "documents-usage", path: "/documents/usage", label: "문서 사용량", icon: <LineChartOutlined />, module: "documents_admin_usage", category: "form_work" },
  { key: "transactions", path: "/transactions", label: "거래내역", icon: <SwapOutlined />, module: "finance", category: "finance" },
  { key: "finance-import", path: "/finance/import", label: "거래 가져오기", icon: <ImportOutlined />, module: "finance", category: "finance" },
  { key: "finance-matching", path: "/finance/matching", label: "매칭 워크북", icon: <LinkOutlined />, module: "finance", category: "finance" },
  { key: "finance-upload-history", path: "/finance/upload-history", label: "업로드 이력", icon: <HistoryOutlined />, module: "finance", category: "finance" },
  { key: "tax-invoices", path: "/tax-invoices", label: "세금계산서", icon: <FileTextOutlined />, module: "finance", category: "finance" },
  { key: "accounts", path: "/accounts", label: "계좌 관리", icon: <BankOutlined />, module: "finance", category: "finance" },
  { key: "settings-categories", path: "/settings/categories", label: "카테고리 관리", icon: <ApartmentOutlined />, module: "finance", category: "settings" },
  { key: "settings-counterparts", path: "/settings/counterparts", label: "거래처 관리", icon: <ContactsOutlined />, module: "finance", category: "settings" },
  { key: "marketing-dashboard", path: "/marketing/dashboard", label: "대시보드", icon: <DashboardOutlined />, module: "marketing_sns", category: "marketing_1" },
  { key: "sns-seoul", path: "/sns/seoul", label: "SNS 콘텐츠", icon: <GlobalOutlined />, module: "marketing_sns", category: "marketing_1" },
  { key: "sns-snapshots", path: "/sns/snapshots", label: "주간 팔로워", icon: <RiseOutlined />, module: "marketing_sns", category: "marketing_1" },
  { key: "sns-content-status", path: "/sns/content-status", label: "콘텐츠 현황", icon: <BarChartOutlined />, module: "marketing_sns", category: "marketing_1" },
  { key: "sns-accounts", path: "/sns/accounts", label: "SNS 계정", icon: <ShareAltOutlined />, module: "marketing_sns", category: "marketing_1" },
  { key: "sns-import", path: "/sns/import", label: "엑셀 가져오기", icon: <CloudUploadOutlined />, module: "marketing_sns", category: "marketing_1" },
  { key: "review-translation", path: "/marketing/review-translation", label: "체험단 번역", icon: <TranslationOutlined />, module: "review_translation", category: "marketing_1" },
  { key: "distribution-dashboard", path: "/distribution/dashboard", label: "대시보드", icon: <DashboardOutlined />, module: "distribution", category: "new_business" },
  { key: "distribution-personas", path: "/distribution/personas", label: "텔레그램 계정", icon: <SendOutlined />, module: "distribution", category: "new_business" },
  { key: "distribution-data-upload", path: "/distribution/data/upload", label: "데이터 업로드", icon: <CloudUploadOutlined />, module: "distribution", category: "new_business" },
  { key: "distribution-data-weekly", path: "/distribution/data/weekly", label: "주차별 종합", icon: <TableOutlined />, module: "distribution", category: "new_business" },
  { key: "distribution-data-products", path: "/distribution/data/products", label: "명품재고대장", icon: <GoldOutlined />, module: "distribution", category: "new_business" },
  { key: "distribution-settlement", path: "/distribution/settlement", label: "정산 / 자금 흐름", icon: <CalculatorOutlined />, module: "distribution", category: "new_business" },
  { key: "distribution-customs", path: "/distribution/customs", label: "면장 (통관신고)", icon: <FileTextOutlined />, module: "distribution", category: "new_business" },
  { key: "distribution-sessions", path: "/distribution/sessions", label: "대화 세션 검수", icon: <CheckSquareOutlined />, module: "distribution", category: "new_business" },
  { key: "distribution-analytics", path: "/distribution/analytics", label: "분석/비용", icon: <LineChartOutlined />, module: "distribution", category: "new_business" },
  // 2026-05-19: admin only 정책 해제 — 일반 직원도 사이드바에 노출. common 그룹.
  { key: "playground", path: "/playground", label: "AI Playground", icon: <RobotOutlined />, module: "playground", category: "common" },
  { key: "playground-library", path: "/playground/library", label: "콘텐츠 라이브러리", icon: <PictureOutlined />, module: "playground", category: "common" },
  // admin 전용 통계 페이지. module=playground_usage 는 admin 만 자동 부여 (registry.ALL_MODULES).
  { key: "workspace-donga", path: "/workspaces/donga", label: "동아제약", icon: <MedicineBoxOutlined />, module: "test_workspace", category: "test_workspace" },
  { key: "workspace-hyundai", path: "/workspaces/hyundai", label: "현대백화점", icon: <ShopOutlined />, module: "test_workspace", category: "test_workspace" },
  { key: "playground-usage", path: "/playground/usage", label: "Playground 사용량", icon: <LineChartOutlined />, module: "playground_usage", category: "system" },
  { key: "playground-admin-sessions", path: "/playground/admin/sessions", label: "Playground 세션 모니터링", icon: <FileSearchOutlined />, module: "playground_admin_sessions", category: "system" },
  { key: "playground-logs", path: "/playground/admin/logs", label: "Playground 로그", icon: <AuditOutlined />, module: "playground_logs", category: "system" },
  { key: "users", path: "/users", label: "사용자 관리", icon: <TeamOutlined />, module: "users", category: "system" },
];

type MenuItem = NonNullable<MenuProps["items"]>[number];

/**
 * 사용자 권한(modules)에 맞춰 사이드바 메뉴 트리를 빌드.
 * 카테고리에 보일 항목이 0개면 그룹 자체를 숨김 → 권한 없는 부서 헤더가 빈 채로 노출되지 않음.
 * 같은 사용자가 여러 부서 권한을 가지면 해당 그룹들이 동시에 노출됨 (중복 부서 권한 케이스).
 */
export function buildSidebarMenuItems(userModules: string[]): MenuItem[] {
  const grouped = new Map<NavCategoryKey, NavItem[]>();
  for (const item of NAV_ITEMS) {
    if (!userModules.includes(item.module)) continue;
    const arr = grouped.get(item.category) ?? [];
    arr.push(item);
    grouped.set(item.category, arr);
  }

  const orderedCategories = (Object.keys(NAV_CATEGORIES) as NavCategoryKey[])
    .sort((a, b) => NAV_CATEGORIES[a].order - NAV_CATEGORIES[b].order);

  const result: MenuItem[] = [];
  for (const category of orderedCategories) {
    const items = grouped.get(category);
    if (!items || items.length === 0) continue;
    const meta = NAV_CATEGORIES[category];
    if (meta.label === null) {
      for (const item of items) {
        result.push({ key: item.path, icon: item.icon, label: item.label });
      }
    } else {
      result.push({
        type: "group",
        key: `group-${category}`,
        label: meta.label,
        children: items.map((item) => ({
          key: item.path,
          icon: item.icon,
          label: item.label,
        })),
      });
    }
  }
  return result;
}

export function getDepartmentLabel(key: string | null | undefined): string {
  if (!key) return "미지정";
  return DEPARTMENTS[key as DepartmentKey] ?? key;
}

export function getRoleLabel(key: string | null | undefined): string {
  if (!key) return "미지정";
  return ROLES[key as RoleKey] ?? key;
}
