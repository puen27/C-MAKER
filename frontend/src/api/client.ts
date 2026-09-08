// 공통 fetch 래퍼 (docs/4-project-principle.md §6 프론트엔드 디렉토리 구조)
//
// 백엔드 API가 준비되면 이 파일의 apiFetch()를 각 *.api.ts 모듈에서 호출하도록 교체한다.
// 현재는 백엔드가 없어 다른 api/*.ts 파일들이 mock 구현을 반환하지만,
// baseURL/토큰 헤더 주입/에러 파싱 규약은 여기에 미리 정의해둔다.

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api';

/** 백엔드 공통 에러 응답 형식 (4-project-principle.md PRIN-06) */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}

export class ApiError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
    this.name = 'ApiError';
  }
}

/** 인증 토큰을 읽어오는 함수. authStore 순환 참조를 피하기 위해 함수 주입 방식을 쓴다. */
let tokenGetter: () => string | null = () => null;

export function registerTokenGetter(getter: () => string | null): void {
  tokenGetter = getter;
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
}

/**
 * 공통 fetch 래퍼. baseURL 결합, 토큰 헤더 주입, 에러 응답 파싱을 일관되게 처리한다.
 * 컴포넌트는 이 함수를 직접 호출하지 않고 queries/ 훅 → api/ 클라이언트를 경유해야 한다.
 */
export async function apiFetch<TResponse>(
  path: string,
  options: RequestOptions = {},
): Promise<TResponse> {
  const token = tokenGetter();
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    let parsed: ApiErrorBody | null = null;
    try {
      parsed = (await response.json()) as ApiErrorBody;
    } catch {
      // 응답 바디가 없거나 JSON이 아닌 경우
    }
    if (parsed?.error) {
      throw new ApiError(parsed.error.code, parsed.error.message);
    }
    throw new ApiError('UNKNOWN', `요청이 실패했습니다 (HTTP ${response.status})`);
  }

  if (response.status === 204) {
    return undefined as TResponse;
  }

  return (await response.json()) as TResponse;
}

/** 사용자에게 보여줄 메시지로 매핑한다. 알 수 없는 에러는 일반 안내 문구로 대체한다. */
export function toUserMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return '요청 처리 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.';
}
