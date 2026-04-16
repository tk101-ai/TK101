/**
 * 범용 유틸리티. shadcn/ui 컴포넌트에서 사용.
 */
import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Tailwind 클래스 병합 (shadcn/ui 컴포넌트 표준).
 *
 * @example
 *   cn("px-2 py-1", condition && "bg-red-500", "px-4")
 *   // 결과: "py-1 bg-red-500 px-4"
 */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
