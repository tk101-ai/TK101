import {
  BankOutlined,
  CloudUploadOutlined,
  DashboardOutlined,
  FileTextOutlined,
  RiseOutlined,
  SearchOutlined,
  ShareAltOutlined,
  SwapOutlined,
  TeamOutlined,
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
  finance: { label: "재무팀", order: 10 },
  marketing_1: { label: "마케팅1팀", order: 20 },
  marketing_2: { label: "마케팅2팀", order: 30 },
  new_business: { label: "신사업팀", order: 40 },
  new_media: { label: "뉴미디어팀", order: 50 },
  design: { label: "디자인팀", order: 60 },
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
  { key: "transactions", path: "/transactions", label: "거래내역", icon: <SwapOutlined />, module: "finance", category: "finance" },
  { key: "tax-invoices", path: "/tax-invoices", label: "세금계산서", icon: <FileTextOutlined />, module: "finance", category: "finance" },
  { key: "accounts", path: "/accounts", label: "계좌 관리", icon: <BankOutlined />, module: "finance", category: "finance" },
  { key: "sns-posts", path: "/sns/posts", label: "SNS 콘텐츠", icon: <FileTextOutlined />, module: "marketing_sns", category: "marketing_1" },
  { key: "sns-snapshots", path: "/sns/snapshots", label: "주간 팔로워", icon: <RiseOutlined />, module: "marketing_sns", category: "marketing_1" },
  { key: "sns-accounts", path: "/sns/accounts", label: "SNS 계정", icon: <ShareAltOutlined />, module: "marketing_sns", category: "marketing_1" },
  { key: "sns-import", path: "/sns/import", label: "엑셀 가져오기", icon: <CloudUploadOutlined />, module: "marketing_sns", category: "marketing_1" },
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
