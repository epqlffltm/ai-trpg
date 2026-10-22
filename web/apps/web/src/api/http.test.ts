// web/apps/web/src/api/http.test.ts
// 서버를 부르는 래퍼: 토큰이 없으면 머리말을 보내지 않고, 401 이면 갱신을 한 번만 하고 한 번만 다시 부른다.

import { describe, expect, it } from 'vitest';
import { installFakeFetch, json, tokens } from '../test/fakeFetch';
import { ApiError } from './errors';
import { apiRequest, isClientError } from './http';
import { REFRESH_PATH } from './refresh';
import { getSession, storeTokens } from './session';

const LISTINGS = '/api/v1/game/listings';
const TABLES = '/api/v1/game/tables';

function signIn(token: string) {
  storeTokens(tokens(token) as never);
}

describe('apiRequest', () => {
  it('토큰이 없으면 Authorization 을 아예 보내지 않는다', async () => {
    const { seen } = installFakeFetch({ [`GET ${LISTINGS}`]: () => json(200, { items: [], total: 0 }) });

    await apiRequest(LISTINGS, { query: { limit: 6, genre: undefined } });

    expect(seen[0]?.headers.has('Authorization')).toBe(false);
    expect(seen[0]?.url).toBe(`${LISTINGS}?limit=6`);
  });

  it('토큰이 있으면 Bearer 로 붙인다', async () => {
    signIn('a1');
    const { seen } = installFakeFetch({ [`GET ${TABLES}`]: () => json(200, { items: [], total: 0 }) });

    await apiRequest(TABLES);

    expect(seen[0]?.headers.get('Authorization')).toBe('Bearer a1');
  });

  it('401 이면 갱신하고 새 토큰으로 한 번 더 부른다', async () => {
    signIn('old');
    const { seen } = installFakeFetch({
      [`GET ${TABLES}`]: (request) =>
        request.headers.get('Authorization') === 'Bearer new'
          ? json(200, { items: [], total: 0 })
          : json(401, { detail: 'expired' }),
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('new')),
    });

    await expect(apiRequest(TABLES)).resolves.toEqual({ items: [], total: 0 });
    expect(seen.map((request) => request.method + ' ' + request.url)).toEqual([
      `GET ${TABLES}`,
      `POST ${REFRESH_PATH}`,
      `GET ${TABLES}`,
    ]);
  });

  it('여러 요청이 한꺼번에 401 을 받아도 갱신은 한 번이다(#30)', async () => {
    signIn('old');
    const { seen } = installFakeFetch({
      [`GET ${TABLES}`]: (request) =>
        request.headers.get('Authorization') === 'Bearer new'
          ? json(200, { items: [], total: 0 })
          : json(401, { detail: 'expired' }),
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('new')),
    });

    await Promise.all([apiRequest(TABLES), apiRequest(TABLES), apiRequest(TABLES)]);

    expect(seen.filter((request) => request.url === REFRESH_PATH)).toHaveLength(1);
  });

  it('갱신도 401 이면 다시 부르지 않고 401 을 던지며 로그인 상태를 비운다', async () => {
    signIn('old');
    const { seen } = installFakeFetch({
      [`GET ${TABLES}`]: () => json(401, { detail: 'expired' }),
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'gone' }),
    });

    const error = await apiRequest(TABLES).catch((caught: unknown) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect(getSession()).toBeNull();
    expect(seen).toHaveLength(2);
  });

  it('토큰 없이 받은 401 은 갱신하지 않는다', async () => {
    const { seen } = installFakeFetch({ [`GET ${TABLES}`]: () => json(401, { detail: 'login' }) });

    await expect(apiRequest(TABLES)).rejects.toBeInstanceOf(ApiError);
    expect(seen).toHaveLength(1);
  });

  it('실패의 본문에서 코드, 기다릴 초, 칸의 오류, 요청 번호를 꺼낸다', async () => {
    installFakeFetch({
      [`POST /api/v1/auth/login`]: () =>
        json(429, { detail: '많다', code: 'too_many_attempts', retry_after: 42, username: ['짧다'] }, { 'X-Request-ID': 'r-1' }),
    });

    const error = (await apiRequest('/api/v1/auth/login', { method: 'POST', body: {} }).catch((e: unknown) => e)) as ApiError;

    expect(error.code).toBe('too_many_attempts');
    expect(error.retryAfter).toBe(42);
    expect(error.fields).toEqual({ username: ['짧다'] });
    expect(error.requestId).toBe('r-1');
    expect(isClientError(error)).toBe(true);
  });

  it('204 는 본문 없이 끝난다', async () => {
    installFakeFetch({ [`POST /api/v1/auth/logout`]: () => new Response(null, { status: 204 }) });

    await expect(apiRequest('/api/v1/auth/logout', { method: 'POST' })).resolves.toBeUndefined();
  });
});
