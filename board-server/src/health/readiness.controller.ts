// board-server/src/health/readiness.controller.ts

/**
 * 서버가 요청을 처리할 준비가 됐는지 확인하는 API. 로그인 없이 부를 수 있고, 내부 정보를 돌려주지 않는다.
 *
 * 프로세스가 살아 있는지(health.controller.ts)와는 묻는 것이 다르다.
 * 여기는 서버가 기대는 것들(지금은 DB)에 닿는지를 본다.
 * 실패해도 관리 도구는 서버를 재시작하지 않는다. 요청을 잠시 보내지 않을 뿐이다.
 */

import {
  Controller,
  Get,
  HttpCode,
  HttpStatus,
  Logger,
  ServiceUnavailableException,
} from '@nestjs/common';
import { DatabaseHealth } from '../database/database.health.js';

/** 준비됐는지의 답의 모양. */
export interface ReadinessResponse {
  status: 'ok' | 'unavailable';
}

@Controller('health/ready')
export class ReadinessController {
  private readonly logger = new Logger(ReadinessController.name);

  constructor(private readonly database: DatabaseHealth) {}

  /**
   * DB 에 닿으면 200, 닿지 않으면 503 을 돌려준다.
   *
   * 왜 닿지 않는지는 응답에 싣지 않는다. 오류의 글에는 DB 주소와 계정 이름이 들어 있다.
   * 로그에도 오류의 종류만 남긴다.
   */
  @Get()
  @HttpCode(HttpStatus.OK)
  async check(): Promise<ReadinessResponse> {
    try {
      await this.database.ping();
    } catch (error) {
      this.logger.warn(`DB 에 닿지 않는다: ${errorName(error)}`);
      const body: ReadinessResponse = { status: 'unavailable' };
      throw new ServiceUnavailableException(body);
    }
    return { status: 'ok' };
  }
}

/** 오류의 종류(클래스 이름). 오류의 글은 쓰지 않는다. */
export function errorName(error: unknown): string {
  return error instanceof Error ? error.constructor.name : typeof error;
}
