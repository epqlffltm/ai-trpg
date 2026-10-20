// board-server/src/observability/pool-metrics.spec.ts

/**
 * 연결을 기다린 시간을 재는 풀(pool-metrics.ts)을 검증한다. 아무도 듣지 않는 포트로 붙어 바로 거절되게 한다.
 * 실제 DB 로 꺼내는 것과 앱이 이 풀을 쓰는지는 test/metrics.e2e-spec.ts 가 본다.
 */

import pg from 'pg';
import { recordMetrics } from '../../test/metrics.js';
import { MeteredPool, meteredPg, poolStats } from './pool-metrics.js';

const metrics = recordMetrics();
/** 아무도 듣고 있지 않은 주소. 연결이 바로 거부된다 */
const NOWHERE = 'postgresql://board:x@127.0.0.1:1/board';

/** 바로 거부되는 풀. */
function refusingPool(): MeteredPool {
  return new MeteredPool({
    connectionString: NOWHERE,
    connectionTimeoutMillis: 1000,
  });
}

describe('MeteredPool', () => {
  it('Promise 로 꺼낸 것도, 실패해도 기다린 시간을 잰다', async () => {
    const pool = refusingPool();
    try {
      await expect(pool.connect()).rejects.toThrow();

      const [wait] = await metrics.current.points('db_pool_wait');
      expect(wait).toMatchObject({ unit: 's', value: 1 });
    } finally {
      await pool.end();
    }
  });

  it('콜백으로 꺼낸 것도 잰다. 콜백은 그대로 불린다(TypeORM 의 길)', async () => {
    const pool = refusingPool();
    try {
      const error = await new Promise<Error | undefined>((resolve) =>
        pool.connect((failed) => resolve(failed)),
      );

      expect(error).toBeInstanceOf(Error);
      expect(await metrics.current.value('db_pool_wait')).toBe(1);
    } finally {
      await pool.end();
    }
  });
});

describe('meteredPg', () => {
  it('Pool 만 바꾸고 나머지는 pg 그대로다. pg-native 를 부르지 않는다', () => {
    const driver = meteredPg();

    expect(driver.Pool).toBe(MeteredPool);
    expect(driver.Client).toBe(pg.Client);
    expect(driver.types).toBe(pg.types);
    expect(Object.keys(driver)).toEqual([]);
  });
});

describe('poolStats', () => {
  it('쉬는 연결과 쓰는 연결을 그때그때 풀에 묻는다', () => {
    const pool = { idleCount: 2, totalCount: 5 } as pg.Pool;

    const stats = poolStats(pool, 10);

    expect([stats.idle(), stats.inUse(), stats.maximum]).toEqual([2, 3, 10]);
  });
});
