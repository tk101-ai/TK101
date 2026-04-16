/**
 * 백엔드 API 호출 래퍼.
 *
 * Sprint 1 auth scope에서 확장 예정:
 * - Access Token 자동 첨부
 * - 401 응답 시 Refresh Token으로 재발급 + 재시도
 * - 공통 에러 포맷 파싱
 */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export class ApiException extends Error {
  constructor(
    public readonly status: number,
    public readonly error: ApiError,
  ) {
    super(error.message);
    this.name = "ApiException";
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
}

/**
 * 공통 fetch 래퍼. JSON 요청/응답 처리.
 */
export async function apiClient<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const { body, headers, ...rest } = options;

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...rest,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  if (!response.ok) {
    let error: ApiError;
    try {
      const payload = await response.json();
      error = payload.error ?? {
        code: "UNKNOWN_ERROR",
        message: `HTTP ${response.status}`,
      };
    } catch {
      error = {
        code: "NETWORK_ERROR",
        message: `HTTP ${response.status}`,
      };
    }
    throw new ApiException(response.status, error);
  }

  // 204 No Content
  if (response.status === 204) {
    return undefined as T;
  }

  const payload = await response.json();
  return payload.data ?? payload;
}
