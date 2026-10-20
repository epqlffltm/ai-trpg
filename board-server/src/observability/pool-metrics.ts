// board-server/src/observability/pool-metrics.ts

/**
 * DB 연결 풀의 메트릭. 풀을 만드는 설정(database/database.options.ts)이 이 풀을 쓰게 한다.
 * 앱이 뜰 때 값을 내보내기 시작한다(database/pool-watch.ts).
 *
 *   - db_pool_connections{state=idle|in_use}: 지금의 연결 수. 수집할 때 풀에 묻는다
 *   - db_pool_connections_max: 풀이 가질 수 있는 가장 많은 연결(POOL_MAX_CONNECTIONS)
 *   - db_pool_wait_seconds: 연결을 얻으려고 기다린 시간. 새 연결을 맺는 시간도 든다(다른 서버와 같다)
 *
 * pg 의 풀에는 "꺼내기 시작"을 알리는 이벤트가 없다(acquire 는 꺼낸 뒤다). 그래서 꺼내는 자리(connect)를 감싼 풀을 쓴다.
 * TypeORM 은 넘겨받은 pg(driver 설정)의 Pool 로 풀을 만든다. pg 를 그대로 두고 Pool 하나만 바꾼 것을 넘긴다(meteredPg).
 * TypeORM 은 콜백으로, pg 의 pool.query 는 안에서 콜백으로 꺼낸다. Promise 로 꺼내는 것도 같이 잰다.
 */

import pg from 'pg';
import { PoolStats, recordPoolWait, secondsSince } from './metrics.js';

/** 꺼낸 뒤에 부르는 콜백(pg 의 모양) */
type ConnectCallback = (
  error: Error | undefined,
  client: pg.PoolClient | undefined,
  done: (release?: unknown) => void,
) => void;

/** 연결을 얻으려고 기다린 시간을 재는 풀. 그 밖은 pg 의 Pool 과 같다. */
export class MeteredPool extends pg.Pool {
  override connect(): Promise<pg.PoolClient>;
  override connect(callback: ConnectCallback): void;
  override connect(callback?: ConnectCallback): Promise<pg.PoolClient> | void {
    const started = performance.now();
    const measure = (): void => recordPoolWait(secondsSince(started));
    if (callback === undefined) {
      return super.connect().finally(measure);
    }
    super.connect((error, client, done) => {
      measure();
      callback(error, client, done);
    });
  }
}

/**
 * TypeORM 에 넘길 pg. pg 를 물려받고 Pool 만 MeteredPool 이다.
 *
 * 펼쳐 복사하지 않는다. pg 의 native 는 읽을 때 pg-native 를 불러오는 getter 다. 물려받으면 읽지 않는 한 부르지 않는다.
 */
export function meteredPg(): typeof pg {
  return Object.create(pg, { Pool: { value: MeteredPool } }) as typeof pg;
}

/** 풀에서 지금의 값을 읽는 것. maximum 은 풀을 만들 때 정한 가장 많은 연결이다. */
export function poolStats(pool: pg.Pool, maximum: number): PoolStats {
  return {
    idle: () => pool.idleCount,
    inUse: () => pool.totalCount - pool.idleCount,
    maximum,
  };
}
