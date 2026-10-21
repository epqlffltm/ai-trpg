// board-server/src/withdrawals/withdrawals.module.ts

/**
 * 탈퇴를 받는 모듈(#603). 인증 서버가 서명해 부르는 주소 하나와, 그 사람의 것을 정리하는 서비스다.
 *
 * 다른 모듈을 가져다 쓰지 않는다. 글, 댓글, 신고, 닉네임, 발송함의 테이블에 SQL 로 직접 닿는다.
 * 모듈마다 서비스를 불러 정리하면 다섯 모듈을 물고, 한 트랜잭션으로 묶기 어렵다.
 */

import { Module } from '@nestjs/common';
import { AuthServerGuard } from './auth-server.guard.js';
import { WithdrawalsController } from './withdrawals.controller.js';
import { WithdrawalsService } from './withdrawals.service.js';

@Module({
  controllers: [WithdrawalsController],
  providers: [WithdrawalsService, AuthServerGuard],
})
export class WithdrawalsModule {}
