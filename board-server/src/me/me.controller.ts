// board-server/src/me/me.controller.ts

/**
 * 토큰의 주인이 누구인지 돌려주는 API. 게임 서버의 /me 와 같은 자리다.
 *
 * 인증 서버가 발급한 토큰을 이 서버가 검증할 수 있는지 확인하는 가장 작은 API 다.
 * 게시판 서버는 사용자의 이름이나 이메일을 모른다. 인증 서버의 public_id 만 안다.
 */

import { Controller, Get, HttpCode, HttpStatus } from '@nestjs/common';
import { CurrentUser } from '../auth/current-user.decorator.js';
// 타입만 가져온다(import type). 데코레이터가 붙은 인자의 타입이 인터페이스면 이렇게 적어야 빌드된다
import type { AccessClaims } from '../auth/tokens.js';

/** 토큰의 주인을 알리는 답의 모양. 이름은 게임 서버의 /me 와 같다. */
export interface MeResponse {
  /** 인증 서버의 public_id */
  user_id: string;
}

@Controller('me')
export class MeController {
  /** 토큰이 유효하면 그 주인의 ID 를 돌려준다. */
  @Get()
  @HttpCode(HttpStatus.OK)
  readMe(@CurrentUser() user: AccessClaims): MeResponse {
    return { user_id: user.userId };
  }
}
