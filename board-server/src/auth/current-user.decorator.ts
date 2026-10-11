// board-server/src/auth/current-user.decorator.ts

/**
 * 요청을 보낸 사람(토큰의 주인)을 컨트롤러의 인자로 받게 해 준다. 게임 서버의 CurrentUser 와 같은 자리다.
 *
 *     @Get('me')
 *     readMe(@CurrentUser() user: AccessClaims) { ... }
 *
 * 값은 문지기(auth.guard.ts)가 토큰을 검증한 뒤 요청에 적어 둔 것이다.
 */

import { createParamDecorator, ExecutionContext } from '@nestjs/common';
import { AccessClaims } from './tokens.js';

/** 문지기를 지난 요청. 검증된 토큰의 값이 user 에 적혀 있다. */
export interface AuthenticatedRequest {
  user?: AccessClaims;
}

/**
 * 요청에 적힌 토큰의 주인을 꺼낸다. 없으면 예외를 낸다.
 *
 * 없는 경우는 하나다. 로그인 없이 부르는 API(@Public)에서 주인을 꺼내려 했다. 코드를 잘못 짠 것이라
 * 조용히 undefined 를 넘기지 않고 500 으로 드러낸다.
 */
export function userOf(request: AuthenticatedRequest): AccessClaims {
  if (request.user === undefined) {
    throw new Error('로그인 없이 부르는 API 에서는 토큰의 주인을 알 수 없다');
  }
  return request.user;
}

/** 컨트롤러의 인자에 붙인다. 토큰의 주인이 들어온다. */
export const CurrentUser = createParamDecorator(
  (_data: unknown, context: ExecutionContext): AccessClaims =>
    userOf(context.switchToHttp().getRequest<AuthenticatedRequest>()),
);
