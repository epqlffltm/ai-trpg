// board-server/src/withdrawals/withdrawal.dto.ts

/**
 * 인증 서버가 보내는 탈퇴의 알림의 본문(auth-server/accounts/withdrawal_client.py).
 *
 *     {"withdrawn_at": "2026-10-28T03:00:00.123456+00:00"}
 *
 * 지우는 일은 이 값을 쓰지 않는다. 빠졌거나 시간대가 없는 시각이면 틀린 알림이다(400). 모르는 칸도 400 이다.
 */

import { IsISO8601, Matches } from 'class-validator';

/** 시각의 끝에 시간대가 있는가(Z 나 +09:00). 인증 서버는 늘 붙인다 */
const WITH_OFFSET = /(Z|[+-]\d{2}:\d{2})$/;

export class WithdrawalDto {
  /** 인증 서버가 계정을 비운 시각(ISO 8601, 시간대 포함) */
  @IsISO8601(
    { strict: true },
    { message: 'withdrawn_at 은 ISO 8601 시각이어야 합니다.' },
  )
  @Matches(WITH_OFFSET, { message: 'withdrawn_at 에 시간대가 있어야 합니다.' })
  withdrawn_at: string;
}
