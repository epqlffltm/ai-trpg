// board-server/src/auth/auth.guard.spec.ts

/**
 * 문지기(auth.guard.ts)를 검증한다. 서버를 띄우지 않고 가짜 검증기를 꽂는다.
 * 검증의 결과가 어떤 응답으로 바뀌는지를 본다. 토큰이 왜 틀렸는지는 tokens.spec.ts 가 본다.
 */

import {
  ExecutionContext,
  HttpException,
  HttpStatus,
  SetMetadata,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import {
  AuthGuard,
  unauthorized,
  verificationUnavailable,
} from './auth.guard.js';
import { AuthenticatedRequest } from './current-user.decorator.js';
import { JwksUnavailableError, REFETCH_INTERVAL_SECONDS } from './jwks.js';
import { IS_PUBLIC, Public } from './public.decorator.js';
import { TokenVerifier } from './token-verifier.js';
import { AccessClaims, InvalidTokenError } from './tokens.js';

const USER: AccessClaims = {
  userId: '0b9f5e0c-6c1d-4f6e-9a57-3f1c2d4e5a6b',
  expiresAt: new Date('2027-01-15T08:00:00.000Z'),
};

/** 문지기가 보는 컨트롤러의 흉내. 표시가 붙은 것과 안 붙은 것이 있다. */
class ClosedController {
  closed(): void {}

  @Public()
  opened(): void {}
}

@Public()
class OpenController {
  inherited(): void {}

  @SetMetadata(IS_PUBLIC, false)
  closedAgain(): void {}
}

/** 문지기에 넘길 요청 하나. 요청, 응답에 붙은 머리말, 실행 맥락을 함께 돌려준다. */
function makeContext(
  authorization: string | undefined,
  handler: () => void = ClosedController.prototype.closed,
  controller: new () => object = ClosedController,
) {
  const request: AuthenticatedRequest & { headers: object } = {
    headers: { authorization },
  };
  const headers = new Map<string, string>();
  const response = {
    setHeader: (name: string, value: string) => headers.set(name, value),
  };
  const context = {
    getHandler: () => handler,
    getClass: () => controller,
    switchToHttp: () => ({
      getRequest: () => request,
      getResponse: () => response,
    }),
  } as unknown as ExecutionContext;
  return { request, headers, context };
}

/** verify 가 정해 둔 대로 끝나는 가짜 검증기를 꽂은 문지기. */
function makeGuard(verify: (token: string) => Promise<AccessClaims>) {
  const verifier = { verify: vi.fn(verify) };
  const guard = new AuthGuard(
    new Reflector(),
    verifier as unknown as TokenVerifier,
  );
  return { guard, verifier };
}

/** 문지기가 낸 예외를 받는다. 들여보냈으면 테스트가 실패한다. */
async function rejection(
  guard: AuthGuard,
  context: ExecutionContext,
): Promise<HttpException> {
  const failure = await guard.canActivate(context).then(
    () => undefined,
    (error: unknown) => error,
  );
  expect(failure).toBeInstanceOf(HttpException);
  return failure as HttpException;
}

describe('AuthGuard', () => {
  it('토큰이 맞으면 들여보내고, 주인을 요청에 적어 둔다', async () => {
    const { guard, verifier } = makeGuard(() => Promise.resolve(USER));
    const { request, context } = makeContext('Bearer good-token');

    await expect(guard.canActivate(context)).resolves.toBe(true);

    expect(verifier.verify).toHaveBeenCalledWith('good-token');
    expect(request.user).toBe(USER);
  });

  it.each([undefined, '', 'Basic dXNlcjpwYXNz', 'Bearer'])(
    '토큰이 없으면(%j) 검증해 보지도 않고 401 이다',
    async (authorization) => {
      const { guard, verifier } = makeGuard(() => Promise.resolve(USER));
      const { headers, context } = makeContext(authorization);

      const failure = await rejection(guard, context);

      expect(failure.getStatus()).toBe(HttpStatus.UNAUTHORIZED);
      expect(headers.get('WWW-Authenticate')).toBe('Bearer');
      expect(verifier.verify).not.toHaveBeenCalled();
    },
  );

  it('토큰이 틀리면 401 이고, 주인을 적지 않는다', async () => {
    const { guard } = makeGuard(() => Promise.reject(new InvalidTokenError()));
    const { request, headers, context } = makeContext('Bearer bad-token');

    const failure = await rejection(guard, context);

    expect(failure.getStatus()).toBe(HttpStatus.UNAUTHORIZED);
    expect(failure.getResponse()).toEqual({ detail: '인증이 필요합니다.' });
    expect(headers.get('WWW-Authenticate')).toBe('Bearer');
    expect(request.user).toBeUndefined();
  });

  it('키를 구할 수 없으면 401 이 아니라 503 이다', async () => {
    const { guard } = makeGuard(() =>
      Promise.reject(new JwksUnavailableError()),
    );
    const { headers, context } = makeContext('Bearer good-token');

    const failure = await rejection(guard, context);

    // 401 을 주면 클라이언트가 멀쩡한 사용자를 로그아웃시킨다
    expect(failure.getStatus()).toBe(HttpStatus.SERVICE_UNAVAILABLE);
    expect(headers.get('Retry-After')).toBe(String(REFETCH_INTERVAL_SECONDS));
    expect(headers.has('WWW-Authenticate')).toBe(false);
  });

  it('뜻밖의 오류는 응답으로 바꾸지 않고 그대로 올린다', async () => {
    const { guard } = makeGuard(() => Promise.reject(new RangeError('버그')));
    const { context } = makeContext('Bearer good-token');

    await expect(guard.canActivate(context)).rejects.toThrow(RangeError);
  });

  it('열어 둔 API 는 토큰 없이 들여보내고, 토큰을 보지 않는다', async () => {
    const { guard, verifier } = makeGuard(() =>
      Promise.reject(new InvalidTokenError()),
    );
    const { request, context } = makeContext(
      'Bearer bad-token',
      ClosedController.prototype.opened,
    );

    await expect(guard.canActivate(context)).resolves.toBe(true);

    expect(verifier.verify).not.toHaveBeenCalled();
    expect(request.user).toBeUndefined();
  });

  it('컨트롤러를 열어 두면 그 안의 API 가 모두 열린다', async () => {
    const { guard } = makeGuard(() => Promise.reject(new InvalidTokenError()));
    const { context } = makeContext(
      undefined,
      OpenController.prototype.inherited,
      OpenController,
    );

    await expect(guard.canActivate(context)).resolves.toBe(true);
  });

  it('API 하나에 붙인 표시가 컨트롤러의 표시보다 먼저다', async () => {
    const { guard } = makeGuard(() => Promise.resolve(USER));
    const { context } = makeContext(
      undefined,
      OpenController.prototype.closedAgain,
      OpenController,
    );

    const failure = await rejection(guard, context);

    expect(failure.getStatus()).toBe(HttpStatus.UNAUTHORIZED);
  });
});

describe('unauthorized', () => {
  it('왜 틀렸는지 알리지 않는다', () => {
    const failure = unauthorized({ setHeader: () => undefined });

    expect(failure.getResponse()).toEqual({ detail: '인증이 필요합니다.' });
  });
});

describe('verificationUnavailable', () => {
  it('잠시 후 다시 해 보라고 알린다', () => {
    const failure = verificationUnavailable({ setHeader: () => undefined });

    expect(failure.getStatus()).toBe(HttpStatus.SERVICE_UNAVAILABLE);
    expect(failure.getResponse()).toEqual({
      detail: '지금은 인증을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.',
    });
  });
});
