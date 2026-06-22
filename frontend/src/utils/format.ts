/**
 * 공통 포맷터 / 색상 상수 (P2-2 DRY 통합).
 *
 * 페이지마다 복붙되어 있던 숫자·금액·날짜 포맷터와 차트 fallback 팔레트를
 * 단일 출처로 모은다. 출력 형식은 기존과 동일하게 유지한다.
 */
import type { Dayjs } from "dayjs";

/** 한국어 천단위 구분 포맷터(재사용 인스턴스). */
export const KR_NUMBER_FORMATTER = new Intl.NumberFormat("ko-KR");

/** number → 한국어 천단위 표기(반올림). null/비유한은 em-dash. */
export function formatNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return KR_NUMBER_FORMATTER.format(Math.round(value));
}

/**
 * Decimal 문자열(또는 number) → 한국어 천단위 표기(반올림). null/빈문자/비유한은 em-dash.
 * number 를 넘기면 `formatNumber` 와 동일 결과를 낸다.
 */
export function formatMoney(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const num = typeof value === "string" ? Number(value) : value;
  if (!Number.isFinite(num)) return "—";
  return KR_NUMBER_FORMATTER.format(Math.round(num));
}

/** 큰 금액을 억/만 단위로 축약(차트 축 라벨용). */
export function formatKRW(value: number): string {
  if (Math.abs(value) >= 1_0000_0000) {
    return `${(value / 1_0000_0000).toFixed(1)}억`;
  }
  if (Math.abs(value) >= 1_0000) {
    return `${(value / 1_0000).toFixed(0)}만`;
  }
  return value.toLocaleString("ko-KR");
}

/** Dayjs → "YYYY-MM-DD" ISO 날짜. null 은 undefined. */
export function toIsoDate(d: Dayjs | null | undefined): string | undefined {
  if (!d) return undefined;
  return d.format("YYYY-MM-DD");
}

/** 카테고리/시리즈에 color 가 없을 때 쓰는 fallback 팔레트(차트 공용). */
export const FINANCE_COLORS = [
  "#1677ff",
  "#722ed1",
  "#52c41a",
  "#fa8c16",
  "#eb2f96",
  "#13c2c2",
  "#fadb14",
  "#a0d911",
] as const;
