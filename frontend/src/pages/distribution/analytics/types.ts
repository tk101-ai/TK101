import type { DistributionCompany } from "../../../api/distribution";

export type CompanyChoice = DistributionCompany | "all";

export interface RangeFilter {
  from?: string;
  to?: string;
  /**
   * 회사 필터 — 백엔드 analytics endpoints 가 아직 미지원일 수 있음.
   * UI 표시·향후 호환용으로만 유지. 현재 빌드된 endpoints 는 무시 처리.
   */
  company_label?: string;
}
