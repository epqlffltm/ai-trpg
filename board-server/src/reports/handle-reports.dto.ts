// board-server/src/reports/handle-reports.dto.ts

/**
 * 운영자가 신고를 처리할 때 받는 값의 모양과 규칙.
 */

import { IsIn } from 'class-validator';
import { REPORT_OUTCOMES } from './reports.policy.js';
// 타입만 가져온다(import type). 칸의 타입으로만 쓴다
import type { ReportOutcome } from './reports.policy.js';

export class HandleReportsDto {
  /** 처리한 결과. 조치함(actioned), 문제없음(dismissed) */
  @IsIn(REPORT_OUTCOMES, {
    message: `outcome 은 ${REPORT_OUTCOMES.join(', ')} 가운데 하나여야 합니다.`,
  })
  outcome: ReportOutcome;
}
