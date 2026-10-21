// board-server/src/withdrawals/auth-server.guard.spec.ts

/**
 * 인증 서버가 서명한 요청만 들여보내는 문지기(auth-server.guard.ts)를 검증한다. 서버도 DB 도 쓰지 않는다.
 * 앱을 통째로 만들어 보는 것은 test/withdrawals.e2e-spec.ts 에 있다.
 */

import { ExecutionContext, UnauthorizedException } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { Environment } from '../config/environment.js';
import { SIGNATURE_HEADER, sign } from '../service-auth/signing.js';
import { AuthServerGuard } from './auth-server.guard.js';

const SECRET = 'board-auth-server-unit-secret-0123456789';
const PATH =
  '/api/v1/board/service/users/6f1e2d3c-4b5a-4c6d-8e7f-0a1b2c3d4e5f/withdrawal';
const BODY = '{"withdrawn_at":"2026-10-28T03:00:00Z"}';

/** 설정에서 비밀만 내주는 가짜. */
function configWith(secret: string): ConfigService<Environment, true> {
  return {
    get: () => secret,
  } as unknown as ConfigService<Environment, true>;
}

/** 요청 하나를 담은 실행의 맥락. rawBody 가 undefined 면 본문의 바이트가 없는 요청이다. */
function contextOf(
  header: string | undefined,
  rawBody: Buffer | undefined,
): ExecutionContext {
  const request = {
    method: 'POST',
    originalUrl: PATH,
    rawBody,
    header: (name: string) => (name === SIGNATURE_HEADER ? header : undefined),
  };
  return {
    switchToHttp: () => ({ getRequest: () => request }),
  } as unknown as ExecutionContext;
}

/** 지금 시각으로 인증 서버처럼 서명한다. */
function signedNow(secret = SECRET, body = BODY): string {
  return sign(secret, Math.floor(Date.now() / 1000), 'POST', PATH, body);
}

describe('AuthServerGuard', () => {
  it('인증 서버의 비밀로 받은 바이트에 한 서명이면 들여보낸다', () => {
    const guard = new AuthServerGuard(configWith(SECRET));

    expect(
      guard.canActivate(contextOf(signedNow(), Buffer.from(BODY, 'utf8'))),
    ).toBe(true);
  });

  it('비밀이 비어 있으면 어떤 서명도 401 이다', () => {
    const guard = new AuthServerGuard(configWith(''));

    expect(() =>
      guard.canActivate(contextOf(signedNow(''), Buffer.from(BODY, 'utf8'))),
    ).toThrow(UnauthorizedException);
  });

  it('본문의 바이트가 없으면 빈 본문으로 본다. 본문에 한 서명은 맞지 않는다', () => {
    const guard = new AuthServerGuard(configWith(SECRET));

    expect(() => guard.canActivate(contextOf(signedNow(), undefined))).toThrow(
      UnauthorizedException,
    );
    expect(guard.canActivate(contextOf(signedNow(SECRET, ''), undefined))).toBe(
      true,
    );
  });

  it('서명이 없으면 401 이다', () => {
    const guard = new AuthServerGuard(configWith(SECRET));

    expect(() =>
      guard.canActivate(contextOf(undefined, Buffer.from(BODY, 'utf8'))),
    ).toThrow(UnauthorizedException);
  });
});
