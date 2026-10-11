// board-server/src/auth/auth.guard.ts

/**
 * 문지기. 요청이 컨트롤러에 닿기 전에 토큰을 꺼내 검증하고, 누가 보낸 요청인지 요청에 적어 둔다.
 *
 * 앱 전체에 건다(auth.module.ts 의 APP_GUARD). 이 서버의 API 는 기본으로 로그인이 필요하고,
 * 열어 둘 API 에만 @Public() 을 붙인다.
 *
 * 검증의 결과를 HTTP 응답으로 바꾸는 일도 여기서 한다. 게임 서버(app/auth/dependencies.py)와 같은 응답이다.
 *   - 토큰이 없거나 틀렸다 -> 401. 클라이언트는 토큰을 갱신하거나 다시 로그인한다.
 *   - 키를 구할 수 없어 확인하지 못했다 -> 503. 클라이언트의 잘못이 아니다. 로그아웃시키면 안 된다.
 */

import {
  CanActivate,
  ExecutionContext,
  HttpException,
  Injectable,
  ServiceUnavailableException,
  UnauthorizedException,
} from '@nestjs/common';
import { Reflector } from '@nestjs/core';
import { readBearerToken } from './bearer.js';
import { AuthenticatedRequest } from './current-user.decorator.js';
import { JwksUnavailableError, REFETCH_INTERVAL_SECONDS } from './jwks.js';
import { IS_PUBLIC } from './public.decorator.js';
import { TokenVerifier } from './token-verifier.js';
import { AccessClaims, InvalidTokenError } from './tokens.js';

/** 문지기가 읽는 요청의 부분. */
interface IncomingRequest extends AuthenticatedRequest {
  headers: { authorization?: string };
}

/** 문지기가 쓰는 응답의 부분. 머리말을 붙인다. */
interface OutgoingResponse {
  setHeader(name: string, value: string): unknown;
}

/**
 * 토큰이 없거나 받아들일 수 없을 때의 응답을 만든다.
 *
 * 이유를 적지 않는다. 만료인지 서명이 틀렸는지를 알려 주면 토큰을 꾸며 내는 쪽에 도움이 된다.
 * WWW-Authenticate 는 401 응답에 붙이게 되어 있는 머리말이다. 어떤 방식으로 인증하는지 알려 준다.
 */
export function unauthorized(response: OutgoingResponse): HttpException {
  response.setHeader('WWW-Authenticate', 'Bearer');
  return new UnauthorizedException({ detail: '인증이 필요합니다.' });
}

/**
 * 토큰이 맞는지 확인할 수 없을 때의 응답을 만든다.
 *
 * Retry-After 는 언제 다시 시도하면 되는지 알려 준다. 키를 다시 가져오는 간격과 같다.
 */
export function verificationUnavailable(
  response: OutgoingResponse,
): HttpException {
  response.setHeader('Retry-After', String(REFETCH_INTERVAL_SECONDS));
  return new ServiceUnavailableException({
    detail: '지금은 인증을 확인할 수 없습니다. 잠시 후 다시 시도해 주세요.',
  });
}

@Injectable()
export class AuthGuard implements CanActivate {
  constructor(
    private readonly reflector: Reflector,
    private readonly verifier: TokenVerifier,
  ) {}

  /** 요청을 들여보낼지 정한다. 들여보낼 때는 토큰의 주인을 요청에 적어 둔다. 아니면 예외를 낸다. */
  async canActivate(context: ExecutionContext): Promise<boolean> {
    if (this.isPublic(context)) {
      return true;
    }
    const http = context.switchToHttp();
    const request = http.getRequest<IncomingRequest>();
    request.user = await this.authenticate(
      request,
      http.getResponse<OutgoingResponse>(),
    );
    return true;
  }

  /** 로그인 없이 부를 수 있다고 표시된 API 인가. API 하나에 붙인 표시가 컨트롤러의 것보다 먼저다. */
  private isPublic(context: ExecutionContext): boolean {
    const marked = this.reflector.getAllAndOverride<boolean | undefined>(
      IS_PUBLIC,
      [context.getHandler(), context.getClass()],
    );
    return marked === true;
  }

  /** 요청의 토큰을 검증하고 그 주인을 돌려준다. 받아들일 수 없으면 응답으로 바꾼 예외를 낸다. */
  private async authenticate(
    request: IncomingRequest,
    response: OutgoingResponse,
  ): Promise<AccessClaims> {
    const token = readBearerToken(request.headers.authorization);
    if (token === undefined) {
      throw unauthorized(response);
    }

    try {
      return await this.verifier.verify(token);
    } catch (error) {
      if (error instanceof InvalidTokenError) {
        throw unauthorized(response);
      }
      if (error instanceof JwksUnavailableError) {
        throw verificationUnavailable(response);
      }
      throw error;
    }
  }
}
