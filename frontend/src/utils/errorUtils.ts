import { isAxiosError } from "axios";

/**
 * 공통 에러 메시지 추출 유틸 (재무 모듈 강화 — typescript-reviewer M-3 정리).
 *
 * - FastAPI 표준 응답: `{"detail": "..."}` 형태의 문자열 detail 우선.
 * - 옵션으로 특정 status 코드별 사용자 친화 메시지를 매핑.
 * - axios 비-axios 에러는 fallback 메시지를 반환.
 *
 * 기존 페이지/컴포넌트마다 중복 정의되어 있던 `extractErrorDetail`를 단일
 * 소스로 모은다.
 */

export interface ExtractErrorOptions {
  /**
   * HTTP status -> 메시지 매핑. axios 에러일 때만 사용된다.
   * 예: `{ 404: "라우터 미등록", 403: "관리자 권한 필요" }`
   */
  statusMessages?: Record<number, string>;
  /**
   * detail 이 비어있고 statusMessages 에도 매칭이 없을 때,
   * axios 에러의 `err.message` 를 fallback 으로 사용할지 여부.
   * 기본값은 `false` (전달된 fallback 인자를 사용).
   */
  useAxiosMessage?: boolean;
}

export function extractErrorDetail(
  err: unknown,
  fallback: string,
  options: ExtractErrorOptions = {},
): string {
  if (isAxiosError(err)) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string" && detail.length > 0) {
      return detail;
    }
    const status = err.response?.status;
    if (status !== undefined && options.statusMessages?.[status]) {
      return options.statusMessages[status];
    }
    if (options.useAxiosMessage && typeof err.message === "string" && err.message.length > 0) {
      return err.message;
    }
  }
  return fallback;
}
