// board-server/src/withdrawals/auth-server.guard.ts

/**
 * 인증 서버가 서명한 요청만 들여보내는 문지기(#603). 탈퇴를 받는 주소(withdrawals.controller.ts)에 붙인다.
 *
 * 사용자의 토큰이 아니라 요청의 서명을 본다(service-auth/signing.ts). 비밀은 AUTH_SERVER_SECRET 이다.
 * 서명은 받은 바이트 그대로에 한다. 그래서 앱이 본문을 읽을 때 원래의 바이트를 남겨 둔다(main.ts 의 rawBody).
 * 경로는 앞부분(/api/v1/board)과 쿼리를 포함한 그대로다. 보내는 쪽이 그렇게 서명한다.
 *
 * 비밀이 비었거나, 서명이 없거나, 틀렸거나, 5분을 넘겼으면 401 이다. 이유를 나누지 않는다.
 * 문지기는 검사(ValidationPipe)보다 먼저 돈다. 서명을 확인하기 전에는 본문의 모양을 알려 주지 않는다.
 */

import {
  CanActivate,
  ExecutionContext,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import type { RawBodyRequest } from '@nestjs/common';
import type { Request } from 'express';
import { Environment } from '../config/environment.js';
import { isValidSignature, SIGNATURE_HEADER } from '../service-auth/signing.js';

/** 서명이 맞지 않을 때의 응답. 무엇이 틀렸는지 싣지 않는다 */
export const BAD_SIGNATURE_DETAIL = '요청의 서명이 맞지 않습니다.';

/** 지금 시각(초). */
function nowSeconds(): number {
  return Math.floor(Date.now() / 1000);
}

@Injectable()
export class AuthServerGuard implements CanActivate {
  constructor(private readonly config: ConfigService<Environment, true>) {}

  canActivate(context: ExecutionContext): boolean {
    const request = context
      .switchToHttp()
      .getRequest<RawBodyRequest<Request>>();
    if (!this.isSignedByAuthServer(request)) {
      throw new UnauthorizedException({ detail: BAD_SIGNATURE_DETAIL });
    }
    return true;
  }

  /** 이 요청이 인증 서버의 비밀로 서명한 것인가. 본문이 없으면 빈 바이트로 본다. */
  private isSignedByAuthServer(request: RawBodyRequest<Request>): boolean {
    return isValidSignature(
      this.config.get('AUTH_SERVER_SECRET', { infer: true }),
      request.header(SIGNATURE_HEADER),
      request.method,
      request.originalUrl,
      request.rawBody ?? Buffer.alloc(0),
      nowSeconds(),
    );
  }
}
