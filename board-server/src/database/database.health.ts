// board-server/src/database/database.health.ts

/**
 * DB 에 닿는지 확인한다. 준비됐는지 묻는 API(health/readiness.controller.ts)가 쓴다.
 *
 * 따로 둔 이유: 그 API 의 테스트가 "DB 에 닿지 않을 때"를 만들려면 이것 하나만 바꿔 꽂으면 된다.
 *
 * 답을 기다리는 시간에 끝이 있다(PING_TIMEOUT_MS). 연결은 됐는데 DB 가 답하지 않고 멈추면, 끝이 없는 확인은
 * 확인하는 쪽(compose 의 healthcheck)이 먼저 포기할 때까지 매달린다. 끝을 두면 그 안에 503 으로 답한다.
 * 결제 서버와 같은 3초다(billing-server 의 ReadinessTimeout).
 *
 * 시간이 지나도 보낸 쿼리는 취소되지 않는다. 그 쿼리는 DB 가 답하거나 연결이 끊길 때까지 풀의 연결 하나를 쥔다.
 * 같은 DB 앞에서는 보통의 요청도 똑같이 연결을 쥐므로, 확인 쪽만 따로 끊으려고 연결을 버리지는 않는다.
 */

import { Injectable } from '@nestjs/common';
import { InjectDataSource } from '@nestjs/typeorm';
import { DataSource } from 'typeorm';

/** DB 의 답을 기다리는 가장 긴 시간(밀리초). compose 의 healthcheck 가 기다리는 5초보다 짧아야 503 이 닿는다 */
export const PING_TIMEOUT_MS = 3000;

/** 정해 둔 시간 안에 DB 가 답하지 않았다. 준비됐는지 묻는 API 는 이 이름을 로그에 남긴다 */
export class PingTimeoutError extends Error {
  constructor(milliseconds: number) {
    super(`${milliseconds}ms 안에 답이 없다`);
  }
}

/**
 * 일이 정해 둔 시간 안에 끝나면 그 결과를, 아니면 PingTimeoutError 를 낸다.
 *
 * 일 자체를 멈추지는 않는다. 늦게 끝난 일의 결과와 오류는 버린다(race 가 받아 두므로 처리되지 않은 거부가 아니다).
 */
export function withinTime<T>(
  work: Promise<T>,
  milliseconds: number,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timeout = new Promise<never>((_, reject) => {
    timer = setTimeout(
      () => reject(new PingTimeoutError(milliseconds)),
      milliseconds,
    );
  });
  return Promise.race([work, timeout]).finally(() => clearTimeout(timer));
}

@Injectable()
export class DatabaseHealth {
  constructor(@InjectDataSource() private readonly dataSource: DataSource) {}

  /** 가장 가벼운 쿼리를 보내 본다. 닿지 않거나 정해 둔 시간 안에 답이 없으면 예외가 난다. */
  async ping(): Promise<void> {
    await withinTime(this.dataSource.query('SELECT 1'), PING_TIMEOUT_MS);
  }
}
