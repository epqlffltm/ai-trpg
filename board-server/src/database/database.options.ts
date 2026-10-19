// board-server/src/database/database.options.ts

/**
 * 설정을 TypeORM 의 연결 옵션으로 바꾼다. Nest 를 모르는 순수한 함수다.
 *
 * 서버(database.module.ts)와 마이그레이션 도구(data-source.ts)가 같은 함수를 쓴다.
 * 둘이 옵션을 따로 적으면, 서버는 board 스키마를 보는데 마이그레이션은 다른 스키마에 테이블을 만드는 일이 생긴다.
 */

import { DataSourceOptions } from 'typeorm';
import { DatabaseSettings } from '../config/environment.js';
import { TracedClient } from '../observability/db-spans.js';

/**
 * DB 에 연결을 맺을 때 기다리는 최대 시간(밀리초).
 * DB 가 응답하지 않을 때 요청이 오래 매달리지 않게 한다
 */
export const CONNECT_TIMEOUT_MS = 5000;

/** PostgreSQL 에 붙는 연결 옵션. TypeORM 의 옵션은 DB 종류마다 모양이 달라서 그중 하나를 고른다 */
export type PostgresOptions = Extract<DataSourceOptions, { type: 'postgres' }>;

/**
 * 연결이 맺어질 때 PostgreSQL 에 넘기는 설정 글자. search_path 를 설정의 스키마로 맞춘다.
 *
 * search_path 는 "스키마 이름 없이 테이블을 부르면 어느 스키마에서 찾는가"다.
 * 연결할 때마다 맞추므로 코드에 스키마 이름을 적지 않아도 되고, 테스트는 설정만 바꿔 테스트용 스키마를 쓴다.
 * 스키마 이름의 모양은 설정을 읽을 때 검사했다(config/environment.ts 의 readDbSchema).
 */
export function searchPathOption(schema: string): string {
  return `-c search_path=${schema}`;
}

/**
 * 설정에서 연결 옵션을 만든다. 이때는 DB 에 연결하지 않는다.
 *
 *   - schema: 엔티티와 마이그레이션 기록 표(migrations)가 놓이는 스키마.
 *   - synchronize 는 늘 끈다. 켜면 서버가 뜰 때 엔티티에 맞춰 테이블을 제멋대로 고친다. 칸을 지우면 데이터도 지워진다.
 *     테이블은 마이그레이션으로만 바꾼다.
 *   - migrationsRun 도 끈다. 서버가 뜨면서 마이그레이션을 돌리지 않는다. 서버가 여러 대면 동시에 돌린다.
 *   - 풀이 맺는 연결은 쿼리마다 span 을 거는 것(TracedClient)이다. 걸린 span 이 없으면 pg 의 것 그대로다
 *     (observability/db-spans.ts).
 */
export function databaseOptions(settings: DatabaseSettings): PostgresOptions {
  return {
    type: 'postgres',
    url: settings.DATABASE_URL,
    connectTimeoutMS: CONNECT_TIMEOUT_MS,
    extra: {
      options: searchPathOption(settings.DB_SCHEMA),
      Client: TracedClient,
    },
    synchronize: false,
    migrationsRun: false,
  };
}
