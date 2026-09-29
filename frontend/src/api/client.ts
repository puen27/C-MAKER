// 공통 fetch 래퍼 (docs/4-project-principle.md §6 프론트엔드 디렉토리 구조)
// baseURL 결합, 토큰 헤더 주입, 공통 에러 응답(PRIN-06) 파싱, 401 시 세션 종료를 일관되게 처리한다.
// 컴포넌트는 이 모듈을 직접 호출하지 않고 queries/ 훅 → api/ 클라이언트를 경유해야 한다.

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
  status: number;

  constructor(code: string, message: string, status: number) {
    super(message);
    this.code = code;
    this.status = status;
    this.name = 'ApiError';
  }
}

/** 인증 토큰을 읽어오는 함수. authStore 순환 참조를 피하기 위해 함수 주입 방식을 쓴다. */
let tokenGetter: () => string | null = () => null;
/** 401(토큰 만료·무효) 응답 시 호출된다 — 로그아웃 처리를 주입받는다. */
let unauthorizedHandler: () => void = () => {};

export function registerTokenGetter(getter: () => string | null): void {
  tokenGetter = getter;
}

export function registerUnauthorizedHandler(handler: () => void): void {
  unauthorizedHandler = handler;
}

interface RequestOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
}

async function request(path: string, options: RequestOptions = {}): Promise<Response> {
  const token = tokenGetter();
  const headers: Record<string, string> = {
    ...(options.body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...(options.headers as Record<string, string> | undefined),
  };

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ApiError('NETWORK_ERROR', '서버에 연결할 수 없습니다. 네트워크 상태를 확인해주세요.', 0);
  }

  if (!response.ok) {
    let parsed: ApiErrorBody | null = null;
    try {
      parsed = (await response.json()) as ApiErrorBody;
    } catch {
      // 응답 바디가 없거나 JSON이 아닌 경우
    }
    // 로그인 실패(LOGIN_FAILED)는 세션 만료가 아니므로 로그아웃 처리하지 않는다.
    if (response.status === 401 && token) {
      unauthorizedHandler();
    }
    if (parsed?.error) {
      throw new ApiError(parsed.error.code, parsed.error.message, response.status);
    }
    throw new ApiError('UNKNOWN', `요청이 실패했습니다 (HTTP ${response.status})`, response.status);
  }
  return response;
}

export async function apiFetch<TResponse>(path: string, options: RequestOptions = {}): Promise<TResponse> {
  const response = await request(path, options);
  if (response.status === 204) {
    return undefined as TResponse;
  }
  return (await response.json()) as TResponse;
}

/** 파일 다운로드 응답을 Blob과 파일명으로 돌려준다(Content-Disposition의 filename* 우선). */
export async function apiDownload(path: string): Promise<{ blob: Blob; filename: string }> {
  const response = await request(path);
  const disposition = response.headers.get('Content-Disposition') ?? '';
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1];
  const plain = /filename="?([^";]+)"?/i.exec(disposition)?.[1];
  const filename = encoded ? decodeURIComponent(encoded) : (plain ?? 'download');
  return { blob: await response.blob(), filename };
}

/** 사용자에게 보여줄 메시지로 매핑한다. 알 수 없는 에러는 일반 안내 문구로 대체한다. */
export function toUserMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.message;
  }
  return '요청 처리 중 문제가 발생했습니다. 잠시 후 다시 시도해주세요.';
}
