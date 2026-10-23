// web/apps/web/src/api/http.ts
// 서버를 부르는 얇은 fetch 래퍼 하나. 모든 서버를 같은 출처(/api/v1/<서버>/)로 부른다.
//
//   - 토큰이 있으면 Authorization 을 붙이고, 없으면 머리말을 아예 보내지 않는다.
//     빈 토큰이나 지난 토큰을 실어 보내면 공개 목록까지 401 이 된다(화면 명세의 A1).
//   - 401 이면 갱신을 한 번만 시도하고 한 번만 다시 부른다. 갱신은 refresh.ts 가 하나로 모은다(#30).
//     그사이 다른 요청이 이미 갱신했으면 다시 갱신하지 않고 새 토큰으로 부른다.
//   - 성공이 아니면 ApiError 를 던진다. 읽기는 TanStack Query 가, 쓰기는 화면이 받는다.

import { ApiError, NetworkError, toApiError } from './errors';
import { refreshSession } from './refresh';
import { getSession } from './session';

export type RequestOptions = {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  /** JSON 으로 보낼 본문 */
  body?: unknown;
  /** 쿼리 문자열. 값이 undefined 면 넣지 않는다 */
  query?: Record<string, string | number | undefined>;
  /** 더 붙일 머리말(결제 서버의 Idempotency-Key 같은 것). 인증과 본문의 머리말은 여기서 덮지 못한다 */
  headers?: Record<string, string>;
  /** 401 에서 갱신하지 않는다(로그인 단계처럼 토큰과 상관없는 요청) */
  skipRefresh?: boolean;
  signal?: AbortSignal;
};

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await sendWithRefresh(withQuery(path, options.query), options);
  if (!response.ok) throw await toApiError(response);
  return readBody<T>(response);
}

async function sendWithRefresh(url: string, options: RequestOptions): Promise<Response> {
  const usedToken = getSession()?.accessToken;
  const first = await send(url, options, usedToken);
  if (first.status !== 401 || usedToken === undefined || options.skipRefresh) return first;
  const token = await tokenAfter401(usedToken);
  return token === null ? first : send(url, options, token);
}

/** 401 을 받은 뒤 다시 부를 토큰. 다른 요청이 이미 바꿨으면 그것, 아니면 갱신한 것. 로그인이 끝났으면 null */
async function tokenAfter401(usedToken: string): Promise<string | null> {
  const latest = getSession()?.accessToken;
  if (latest !== undefined && latest !== usedToken) return latest;
  const renewed = await refreshSession();
  return renewed?.accessToken ?? null;
}

async function send(url: string, options: RequestOptions, token: string | undefined): Promise<Response> {
  try {
    return await fetch(url, {
      method: options.method ?? 'GET',
      headers: headersFor(options, token),
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      credentials: 'same-origin',
      signal: options.signal ?? null,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new NetworkError(error);
  }
}

function headersFor(options: RequestOptions, token: string | undefined): Headers {
  const headers = new Headers({ ...options.headers, Accept: 'application/json' });
  if (options.body !== undefined) headers.set('Content-Type', 'application/json');
  if (token !== undefined) headers.set('Authorization', `Bearer ${token}`);
  return headers;
}

function withQuery(path: string, query: RequestOptions['query']): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(query)) {
    if (value !== undefined) params.set(name, String(value));
  }
  const text = params.toString();
  return text ? `${path}?${text}` : path;
}

/** 본문이 없으면(204) undefined. 나머지는 JSON 이다 */
async function readBody<T>(response: Response): Promise<T> {
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** 다시 시도해도 같은 답일 실패인가(4xx). 읽기의 자동 재시도를 막는 데 쓴다 */
export function isClientError(error: unknown): boolean {
  return error instanceof ApiError && error.status >= 400 && error.status < 500;
}
