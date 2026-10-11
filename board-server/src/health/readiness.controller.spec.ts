// board-server/src/health/readiness.controller.spec.ts

/**
 * 준비됐는지 확인하는 API 를 검증한다. 서버도 DB 도 띄우지 않고 가짜 확인기를 꽂는다.
 * 주소와 상태 코드는 test/health.e2e-spec.ts 가 본다.
 */

import { HttpStatus, Logger } from '@nestjs/common';
import { DatabaseHealth } from '../database/database.health.js';
import {
  errorName,
  ReadinessController,
  StatusSetter,
} from './readiness.controller.js';

/** 드라이버가 내는 오류의 흉내. 글에 계정 이름이 들어 있다 */
class ConnectionRefused extends Error {}

/** ping 이 정해 둔 대로 끝나는 가짜 확인기. */
function makeDatabase(ping: () => Promise<void>): DatabaseHealth {
  return { ping } as DatabaseHealth;
}

/** 정해진 상태 코드를 기억하는 가짜 응답. */
function makeResponse(): StatusSetter & { code?: number } {
  const response: StatusSetter & { code?: number } = {
    status: (code: number) => (response.code = code),
  };
  return response;
}

describe('ReadinessController', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('DB 에 닿으면 200 으로 준비됐다고 답한다', async () => {
    const controller = new ReadinessController(
      makeDatabase(() => Promise.resolve()),
    );
    const response = makeResponse();

    await expect(controller.check(response)).resolves.toEqual({
      status: 'ok',
    });
    expect(response.code).toBe(HttpStatus.OK);
  });

  it('DB 에 닿지 않으면 503 으로 준비되지 않았다고 답한다', async () => {
    vi.spyOn(Logger.prototype, 'warn').mockImplementation(() => undefined);
    const controller = new ReadinessController(
      makeDatabase(() => Promise.reject(new ConnectionRefused('끊겼다'))),
    );
    const response = makeResponse();

    // 예외를 던지지 않는다. 준비되지 않았다는 것은 이 API 의 답이다
    await expect(controller.check(response)).resolves.toEqual({
      status: 'unavailable',
    });
    expect(response.code).toBe(HttpStatus.SERVICE_UNAVAILABLE);
  });

  it('로그에는 오류의 종류만 남긴다', async () => {
    const warn = vi
      .spyOn(Logger.prototype, 'warn')
      .mockImplementation(() => undefined);
    const secret = 'password authentication failed for user "board"';
    const controller = new ReadinessController(
      makeDatabase(() => Promise.reject(new ConnectionRefused(secret))),
    );

    await controller.check(makeResponse());

    // 오류의 글에는 DB 주소와 계정 이름이 들어 있다. 로그에 싣지 않는다
    expect(warn).toHaveBeenCalledWith('DB 에 닿지 않는다: ConnectionRefused');
  });
});

describe('errorName', () => {
  it('오류의 클래스 이름을 돌려준다', () => {
    expect(errorName(new ConnectionRefused('글'))).toBe('ConnectionRefused');
    expect(errorName(new Error('글'))).toBe('Error');
  });

  it('오류가 아닌 것이 던져졌으면 그 종류를 돌려준다', () => {
    expect(errorName('글')).toBe('string');
  });
});
