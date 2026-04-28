import { BankOutlined, DashboardOutlined, FileTextOutlined, SwapOutlined, TeamOutlined } from "@ant-design/icons";
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

export interface NavItem {
  key: string;
  path: string;
  label: string;
  icon: ReactNode;
  module: string;
}

export const NAV_ITEMS: NavItem[] = [
  { key: "dashboard", path: "/", label: "대시보드", icon: <DashboardOutlined />, module: "dashboard" },
  { key: "transactions", path: "/transactions", label: "거래내역", icon: <SwapOutlined />, module: "finance" },
  { key: "tax-invoices", path: "/tax-invoices", label: "세금계산서", icon: <FileTextOutlined />, module: "finance" },
  { key: "accounts", path: "/accounts", label: "계좌 관리", icon: <BankOutlined />, module: "finance" },
  { key: "users", path: "/users", label: "사용자 관리", icon: <TeamOutlined />, module: "users" },
];

export function getDepartmentLabel(key: string | null | undefined): string {
  if (!key) return "미지정";
  return DEPARTMENTS[key as DepartmentKey] ?? key;
}

export function getRoleLabel(key: string | null | undefined): string {
  if (!key) return "미지정";
  return ROLES[key as RoleKey] ?? key;
}
