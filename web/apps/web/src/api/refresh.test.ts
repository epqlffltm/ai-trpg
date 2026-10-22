// web/apps/web/src/api/refresh.test.ts
// 갱신이 한 번에 하나만 가는지(#30), 401 과 그 밖의 실패를 다르게 다루는지 본다.

import { describe, expect, it } from 'vitest';
import { installFakeFetch, json, tokens } from '../test/fakeFetch';
import { ApiError } from './errors';
import { REFRESH_PATH, refreshSession } from './refresh';
import { getSession, storeTokens } from './session';

describe('refreshSession', () => {
  it('한꺼번에 여러 번 불러도 서버에는 한 번만 간다', async () => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const { seen } = installFakeFetch({
      [`POST ${REFRESH_PATH}`]: async () => {
        await gate;
        return json(200, tokens('new-token'));
      },
    });

    const calls = [refreshSession(), refreshSession(), refreshSession()];
    release();
    const sessions = await Promise.all(calls);

    expect(seen).toHaveLength(1);
    expect(sessions.map((session) => session?.accessToken)).toEqual(['new-token', 'new-token', 'new-token']);
    expect(getSession()?.accessToken).toBe('new-token');
  });

  it('끝난 뒤에 다시 부르면 새로 간다', async () => {
    const { seen } = installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(200, tokens('t')) });

    await refreshSession();
    await refreshSession();

    expect(seen).toHaveLength(2);
  });

  it('401 이면 로그인이 끝난 것이라 상태를 비우고 null 을 준다', async () => {
    storeTokens(tokens('old') as never);
    installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no' }) });

    await expect(refreshSession()).resolves.toBeNull();
    expect(getSession()).toBeNull();
  });

  it('503 이면 로그아웃시키지 않고 오류를 던진다', async () => {
    storeTokens(tokens('old') as never);
    installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(503, { detail: '잠시 뒤에' }) });

    await expect(refreshSession()).rejects.toBeInstanceOf(ApiError);
    expect(getSession()?.accessToken).toBe('old');
  });

  it('쿠키를 함께 보낸다(같은 출처)', async () => {
    const { fetchMock } = installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(200, tokens('t')) });

    await refreshSession();

    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: 'POST', credentials: 'same-origin' });
  });
});
