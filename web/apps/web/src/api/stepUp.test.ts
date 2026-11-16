// web/apps/web/src/api/stepUp.test.ts
// 본인 확인의 부르기: 토큰에 세션의 이름이 없다는 답(409)이면 한 번 갱신하고 다시 부르는지,
// 갱신하지 못하면 처음 답을 던지는지 본다.

import { describe, expect, it } from 'vitest';
import { installFakeFetch, json, tokens } from '../test/fakeFetch';
import { ApiError } from './errors';
import { REFRESH_PATH } from './refresh';
import { storeTokens } from './session';
import { fetchStepUp, verifyStepUp } from './stepUp';

const STEP_UP = '/api/v1/auth/me/step-up';
const UNKNOWN = { detail: 'x', code: 'step_up_session_unknown' };
const OPEN = { enabled: true, open: true, expires_at: '2026-11-16T01:10:00Z' };

describe('stepUp', () => {
  it('세션의 이름이 없는 옛 토큰이면 갱신하고 새 토큰으로 다시 부른다', async () => {
    storeTokens(tokens('old') as never);
    const { seen } = installFakeFetch({
      [`POST ${STEP_UP}`]: (request) =>
        request.headers.get('Authorization') === 'Bearer new' ? json(200, OPEN) : json(409, UNKNOWN),
      [`POST ${REFRESH_PATH}`]: () => json(200, tokens('new')),
    });

    await expect(verifyStepUp('123456')).resolves.toEqual(OPEN);
    expect(seen.map((request) => `${request.method} ${request.url}`)).toEqual([
      `POST ${STEP_UP}`,
      `POST ${REFRESH_PATH}`,
      `POST ${STEP_UP}`,
    ]);
  });

  it('갱신하지 못하면(로그인이 끝남) 처음 답을 던진다', async () => {
    storeTokens(tokens('old') as never);
    installFakeFetch({
      [`GET ${STEP_UP}`]: () => json(409, UNKNOWN),
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'x' }),
    });

    const error = await fetchStepUp().catch((caught: unknown) => caught);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe('step_up_session_unknown');
  });
});
