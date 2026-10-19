// board-server/src/database/database.options.spec.ts

/**
 * 설정을 연결 옵션으로 바꾸는 함수(database.options.ts)를 검증한다. DB 에 연결하지 않는다.
 * 실제로 그 스키마에 붙는지는 test/database.e2e-spec.ts 가 본다.
 */

import { TracedClient } from '../observability/db-spans.js';
import {
  CONNECT_TIMEOUT_MS,
  databaseOptions,
  searchPathOption,
} from './database.options.js';

const SETTINGS = {
  DATABASE_URL: 'postgresql://board:secret-password@127.0.0.1:5432/trpg',
  DB_SCHEMA: 'board_test',
};

describe('databaseOptions', () => {
  it('설정의 주소로 PostgreSQL 에 붙는다', () => {
    const options = databaseOptions(SETTINGS);

    expect(options.type).toBe('postgres');
    expect(options.url).toBe(SETTINGS.DATABASE_URL);
  });

  it('연결할 때마다 search_path 를 설정의 스키마로 맞춘다', () => {
    const options = databaseOptions(SETTINGS);

    expect(options.extra).toEqual({
      options: '-c search_path=board_test',
      Client: TracedClient,
    });
  });

  it('스키마 이름을 옵션에 따로 적지 않는다', () => {
    // 적으면 TypeORM 이 만드는 SQL 에 스키마 이름이 박힌다.
    // 같은 마이그레이션을 개발용과 테스트용 스키마에 함께 쓸 수 없게 된다
    expect(databaseOptions(SETTINGS).schema).toBeUndefined();
  });

  it('테이블을 엔티티에 맞춰 제멋대로 고치지 않는다', () => {
    const options = databaseOptions(SETTINGS);

    // 테이블은 마이그레이션으로만 바꾼다. 서버가 뜨면서 돌리지도 않는다
    expect(options.synchronize).toBe(false);
    expect(options.migrationsRun).toBe(false);
  });

  it('응답 없는 DB 를 하염없이 기다리지 않는다', () => {
    expect(databaseOptions(SETTINGS).connectTimeoutMS).toBe(CONNECT_TIMEOUT_MS);
  });
});

describe('searchPathOption', () => {
  it('PostgreSQL 에 넘기는 설정 글자를 만든다', () => {
    expect(searchPathOption('board')).toBe('-c search_path=board');
  });
});
