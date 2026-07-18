/**
 * 공용 API 클라이언트
 * - NEXT_PUBLIC_API_URL 기반 (하드코딩 localhost 금지)
 * - Bearer 토큰 자동 첨부
 * - response.ok 체크 후 에러를 타입 있는 결과로 반환 (throw 아님 — 호출부가 항상 성공/실패를 분기)
 * - 401 시 /login 리다이렉트
 *
 * 08_api-contract.md 에러 카탈로그(E-4xx/E-5xx) 및 04_frd.md FR-201 인수 조건
 * ("response.ok 미확인 상태로 에러 JSON을 결과로 세팅해 렌더링하지 않는다") 준수.
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export interface ApiError {
  status: number;
  errorCode?: string;
  message: string;
}

export interface ApiSuccess<T> {
  ok: true;
  data: T;
}

export interface ApiFailure {
  ok: false;
  error: ApiError;
}

export type ApiResult<T> = ApiSuccess<T> | ApiFailure;

/**
 * `tsconfig.json`의 `strict: false`(strictNullChecks 비활성) 환경에서는
 * discriminated union의 `if (result.ok)` 좁히기가 정상 동작하지 않는다(TS 알려진 제약).
 * 호출부는 `result.ok` 직접 분기 대신 이 타입가드를 사용해 안전하게 좁힌다.
 */
export function isApiSuccess<T>(result: ApiResult<T>): result is ApiSuccess<T> {
  return result.ok === true;
}

function getStoredToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return localStorage.getItem('token') || sessionStorage.getItem('token');
  } catch {
    return null;
  }
}

function redirectToLogin() {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem('token');
    sessionStorage.removeItem('token');
  } catch {
    // storage 접근 실패는 무시하고 리다이렉트는 계속 진행
  }
  window.location.href = '/login';
}

async function parseErrorBody(response: Response): Promise<{ errorCode?: string; message: string }> {
  try {
    const body = await response.json();
    return {
      errorCode: body.error_code,
      message: body.message || body.detail || '요청 처리 중 오류가 발생했습니다.',
    };
  } catch {
    return { message: '백엔드 서버에 연결할 수 없습니다.' };
  }
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  token?: string | null;
  body?: unknown;
  /** true면 401 발생 시에도 자동 리다이렉트하지 않는다 (로그인 화면 자체 등) */
  skipAuthRedirect?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<ApiResult<T>> {
  const { token, body, skipAuthRedirect, headers, ...rest } = options;
  const authToken = token !== undefined ? token : getStoredToken();

  const finalHeaders: Record<string, string> = {
    ...(headers as Record<string, string> | undefined),
  };

  let finalBody: BodyInit | undefined;
  if (body !== undefined) {
    if (body instanceof FormData) {
      finalBody = body;
    } else {
      finalHeaders['Content-Type'] = finalHeaders['Content-Type'] || 'application/json';
      finalBody = JSON.stringify(body);
    }
  }

  if (authToken) {
    finalHeaders['Authorization'] = `Bearer ${authToken}`;
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...rest,
      headers: finalHeaders,
      body: finalBody,
    });
  } catch (networkError) {
    return {
      ok: false,
      error: { status: 0, message: '서버 연결 실패 — 네트워크 상태를 확인해주세요.' },
    };
  }

  if (response.status === 401) {
    if (!skipAuthRedirect) {
      redirectToLogin();
    }
    const { errorCode, message } = await parseErrorBody(response);
    return { ok: false, error: { status: 401, errorCode, message } };
  }

  if (!response.ok) {
    const { errorCode, message } = await parseErrorBody(response);
    return { ok: false, error: { status: response.status, errorCode, message } };
  }

  if (response.status === 204) {
    return { ok: true, data: undefined as T };
  }

  try {
    const data = (await response.json()) as T;
    return { ok: true, data };
  } catch {
    return {
      ok: false,
      error: { status: response.status, message: '응답을 처리할 수 없습니다.' },
    };
  }
}

export const apiClient = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: 'GET' }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'POST', body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: 'PUT', body }),
  delete: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: 'DELETE' }),
};

export { BASE_URL as API_BASE_URL };
