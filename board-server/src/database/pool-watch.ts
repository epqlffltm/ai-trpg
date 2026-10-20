// board-server/src/database/pool-watch.ts

/**
 * 앱이 뜬 뒤 TypeORM 이 만든 연결 풀을 메트릭으로 내보내기 시작한다(observability/pool-metrics.ts).
 *
 * 풀은 TypeORM 의 안에 있다(PostgresDriver 의 master). 안쪽 이름이라 TypeORM 의 판이 바뀌면 사라질 수 있다.
 * 그때는 풀의 메트릭만 빠지고 앱은 그대로 뜬다. 테스트(test/metrics.e2e-spec.ts)가 풀이 걸렸는지 본다.
 */

import { Injectable, OnApplicationBootstrap } from '@nestjs/common';
import { InjectDataSource } from '@nestjs/typeorm';
import pg from 'pg';
import { DataSource } from 'typeorm';
import { watchPool } from '../observability/metrics.js';
import { poolStats } from '../observability/pool-metrics.js';
import { POOL_MAX_CONNECTIONS } from './database.options.js';

/** 데이터 소스의 연결 풀. 없거나 pg 의 풀이 아니면 undefined 다. */
export function poolOf(dataSource: DataSource): pg.Pool | undefined {
  const master: unknown = (dataSource.driver as { master?: unknown }).master;
  return master instanceof pg.Pool ? master : undefined;
}

@Injectable()
export class PoolWatch implements OnApplicationBootstrap {
  constructor(@InjectDataSource() private readonly dataSource: DataSource) {}

  /** 앱이 뜬 뒤 한 번 부른다. 이 앱의 풀로 바꾼다. */
  onApplicationBootstrap(): void {
    const pool = poolOf(this.dataSource);
    watchPool(
      pool === undefined ? undefined : poolStats(pool, POOL_MAX_CONNECTIONS),
    );
  }
}
