// board-server/src/health/readiness.controller.ts

/**
 * 서버가 요청을 처리할 준비가 됐는지 확인하는 API. 로그인 없이 부를 수 있고, 내부 정보를 돌려주지 않는다.
 *
 * 프로세스가 살아 있는지(health.controller.ts)와는 묻는 것이 다르다.
 * 여기는 서버가 기대는 것들(지금은 DB)에 닿는지를 본다.
 * 실패해도 관리 도구는 서버를 재시작하지 않는다. 요청을 잠시 보내지 않을 뿐이다.
 * 확인한 결과를 메트릭 db_up 으로 적는다(1 이면 닿는다). compose 의 healthcheck 가 10초마다 부른다.
 */

import { Controller, Get, HttpStatus, Logger, Res } from '@nestjs/common';
import { Public } from '../auth/public.decorator.js';
import { DatabaseHealth } from '../database/database.health.js';
import { recordDbUp } from '../observability/metrics.js';
import { ReadinessResponse } from './health.response.js';

/** 이 API 가 쓰는 응답의 부분. 상태 코드를 정한다. */
export interface StatusSetter {
  status(code: number): unknown;
}

@Public()
@Controller('health/ready')
export class ReadinessController {
  private readonly logger = new Logger(ReadinessController.name);

  constructor(private readonly database: DatabaseHealth) {}

  /**
   * DB 에 닿으면 200, 닿지 않으면 503 을 돌려준다.
   *
   * 왜 닿지 않는지는 응답에 싣지 않는다. 오류의 글에는 DB 주소와 계정 이름이 들어 있다.
   * 로그에도 오류의 종류만 남긴다.
   *
   * 준비되지 않았다는 것은 오류가 아니라 이 API 의 답이다. 그래서 예외를 던지지 않고 상태 코드만 바꾼다.
   * 예외로 던지면 오류 응답의 모양({ detail })으로 바뀐다. 이 주소는 관리 도구가 읽는 것이라 답의 모양을 지킨다.
   */
  @Get()
  async check(
    @Res({ passthrough: true }) response: StatusSetter,
  ): Promise<ReadinessResponse> {
    try {
      await this.database.ping();
    } catch (error) {
      recordDbUp(false);
      this.logger.warn(`DB 에 닿지 않는다: ${errorName(error)}`);
      response.status(HttpStatus.SERVICE_UNAVAILABLE);
      return { status: 'unavailable' };
    }
    recordDbUp(true);
    response.status(HttpStatus.OK);
    return { status: 'ok' };
  }
}

/** 오류의 종류(클래스 이름). 오류의 글은 쓰지 않는다. */
export function errorName(error: unknown): string {
  return error instanceof Error ? error.constructor.name : typeof error;
}
