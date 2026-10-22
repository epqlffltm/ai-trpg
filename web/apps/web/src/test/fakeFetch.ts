// web/apps/web/src/test/fakeFetch.ts
// 시험에서 서버 대신 답하는 가짜 fetch. 주소마다 답을 정하고, 받은 요청을 적어 둔다.
// 답은 함수라서 같은 주소에 차례로 다른 답을 줄 수 있다. 정하지 않은 주소는 시험을 실패시킨다.

import { vi } from 'vitest';

export type SeenRequest = { url: string; method: string; headers: Headers; body: unknown; signal: AbortSignal | null };
type Handler = (request: SeenRequest) => Response | Promise<Response>;

export function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

export function installFakeFetch(routes: Record<string, Handler>) {
  const seen: SeenRequest[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init: RequestInit = {}) => {
    const url = String(input);
    const request: SeenRequest = {
      url,
      method: init.method ?? 'GET',
      headers: new Headers(init.headers),
      body: typeof init.body === 'string' ? JSON.parse(init.body) : undefined,
      signal: init.signal ?? null,
    };
    seen.push(request);
    const key = `${request.method} ${url.split('?')[0]}`;
    const handler = routes[key];
    if (!handler) throw new Error(`정하지 않은 요청: ${key}`);
    return handler(request);
  });
  vi.stubGlobal('fetch', fetchMock);
  return { seen, fetchMock };
}

/** 토큰을 주는 응답의 본문(LoginResponse) */
export function tokens(accessToken: string, extra: Record<string, unknown> = {}) {
  return {
    access_token: accessToken,
    token_type: 'Bearer',
    expires_in: 900,
    consents_pending: [],
    withdrawal_scheduled_at: null,
    ...extra,
  };
}
