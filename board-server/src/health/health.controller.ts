// board-server/src/health/health.controller.ts

/**
 * 서버 프로세스가 살아 있는지 확인하는 API. 로그인 없이 부를 수 있고, 내부 정보를 돌려주지 않는다.
 *
 * 배포 환경의 프록시나 컨테이너 관리 도구가 주기적으로 부른다. 실패하면 관리 도구가 서버를 재시작한다.
 * API 주소(/api/v1/board) 밖에 둔다(app.setup.ts). 사람이 아니라 도구가 부르는 주소라 버전이 없다.
 */

import { Controller, Get, HttpCode, HttpStatus } from '@nestjs/common';
import { Public } from '../auth/public.decorator.js';

/** 살아 있다는 답의 모양. */
export interface HealthResponse {
  status: 'ok';
}

@Public()
@Controller('health')
export class HealthController {
  /**
   * 서버 프로세스가 요청을 받을 수 있으면 200 을 돌려준다.
   *
   * DB 나 다른 서버의 상태는 보지 않는다. 그것까지 보면, DB 가 잠깐 느려졌을 때
   * 관리 도구가 멀쩡한 서버를 죽은 것으로 보고 재시작한다.
   */
  @Get()
  @HttpCode(HttpStatus.OK)
  check(): HealthResponse {
    return { status: 'ok' };
  }
}
