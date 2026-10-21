// board-server/src/withdrawals/withdrawals.controller.ts

/**
 * 인증 서버가 탈퇴를 알리는 API(#603, docs/architecture/withdrawal.md 의 "알리는 길"). 인증 서버만 부른다.
 *
 *   POST /service/users/:userId/withdrawal    {"withdrawn_at": "..."}  ->  200 {"status": "processed"}
 *
 * 사용자의 토큰이 아니라 인증 서버의 서명을 본다(auth-server.guard.ts). 그래서 로그인의 문지기는 비켜 둔다(@Public).
 * 인증 서버는 200 과 processed 를 받을 때까지 다시 보낸다. 몇 번을 받아도 같고, 모르는 사람이어도 200 이다.
 * 서명이 틀리면 401, 주소의 번호나 본문이 틀리면 400 이다. 둘 다 인증 서버는 다시 보낸다(코드의 버그다).
 */

import {
  Body,
  Controller,
  HttpCode,
  HttpStatus,
  Logger,
  Param,
  ParseUUIDPipe,
  Post,
  UseGuards,
} from '@nestjs/common';
import { ApiHeader } from '@nestjs/swagger';
import { Public } from '../auth/public.decorator.js';
import { SIGNATURE_HEADER } from '../service-auth/signing.js';
import { AuthServerGuard } from './auth-server.guard.js';
import { WithdrawalDto } from './withdrawal.dto.js';
import {
  WITHDRAWAL_PROCESSED,
  WithdrawalResponse,
} from './withdrawal.response.js';
import { Erased, WithdrawalsService } from './withdrawals.service.js';

/** 로그의 operation(docs/observability.md) */
export const WITHDRAWAL_OPERATION = 'board.withdrawal';

@Public()
@ApiHeader({
  name: SIGNATURE_HEADER,
  required: true,
  description:
    '인증 서버의 서명(t=<초>,v1=<HMAC>). 비밀은 AUTH_SERVER_SECRET 이다. 틀리면 401',
})
@Controller('service/users')
@UseGuards(AuthServerGuard)
export class WithdrawalsController {
  private readonly logger = new Logger(WithdrawalsController.name);

  constructor(private readonly withdrawals: WithdrawalsService) {}

  /** 그 사람의 글과 댓글의 글쓴이, 신고한 사람을 비우고 닉네임과 보낼 알림을 지운다. */
  @Post(':userId/withdrawal')
  @HttpCode(HttpStatus.OK)
  async receive(
    @Param('userId', new ParseUUIDPipe()) userId: string,
    // 본문은 검사만 한다. 지우는 일은 이 값을 쓰지 않는다
    @Body() _withdrawal: WithdrawalDto,
  ): Promise<WithdrawalResponse> {
    this.logErased(await this.withdrawals.erase(userId));
    return { status: WITHDRAWAL_PROCESSED };
  }

  /** 정리한 수를 남긴다. 사람(user_id)은 남기지 않는다. */
  private logErased(erased: Erased): void {
    this.logger.log({
      message: '탈퇴한 사람의 것을 정리했다',
      operation: WITHDRAWAL_OPERATION,
      blanked_posts: erased.posts,
      blanked_comments: erased.comments,
      blanked_reports: erased.reports,
      deleted_authors: erased.authors,
      deleted_notifications: erased.notifications,
    });
  }
}
