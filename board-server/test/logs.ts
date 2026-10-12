// board-server/test/logs.ts

/**
 * 서버가 남기는 로그 줄을 화면에 찍지 않고 모은다. 일부러 5xx 를 만드는 테스트가 쓴다.
 *
 * 5xx 에는 오류 로그(level: error)가 남는다(docs/observability.md). 지켜야 할 동작이지만, 테스트가 일부러 만든 것이
 * 화면에 ERROR 로 찍히면 실패처럼 보인다. 그런 줄에 익숙해지면 진짜 ERROR 도 지나치게 된다.
 * 그래서 그런 테스트는 줄을 모아 두고 "오류 줄이 남았다"를 확인한다. 소음이 검사로 바뀐다.
 *
 * 서버가 쓰는 것과 같은 로거(JsonLogger)를 꽂는다. 나가는 줄의 모양도 서버와 같다.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import { JsonLogger } from '../src/observability/json-logger.js';

/** 모은 로그. */
export interface CapturedLogs {
  /** 나간 줄들. JSON 한 줄씩이다 */
  readonly lines: string[];
  /** 요청이 끝났다는 줄 가운데 이 상태 코드로 끝난 것들. */
  finishedWith(statusCode: number): Record<string, unknown>[];
}

/** 이 앱의 로그를 모으기 시작한다. 앱을 닫을 때까지 화면에는 아무것도 찍지 않는다. */
export function captureLogs(app: NestExpressApplication): CapturedLogs {
  const lines: string[] = [];
  app.useLogger(
    new JsonLogger(
      { service: 'board-server', environment: 'test', version: 'test' },
      'info',
      (line) => lines.push(line),
    ),
  );
  return {
    lines,
    finishedWith: (statusCode) =>
      lines
        .map((line) => JSON.parse(line) as Record<string, unknown>)
        .filter((entry) => entry.status_code === statusCode),
  };
}
