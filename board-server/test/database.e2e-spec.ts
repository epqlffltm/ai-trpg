// board-server/test/database.e2e-spec.ts

/**
 * DB 연결을 검증한다. 테스트가 정말로 테스트용 스키마에서, 게시판 서버의 계정으로 도는가.
 * 그리고 그 계정이 다른 서버의 스키마에 들어가지 못하는가.
 */

import { NestExpressApplication } from '@nestjs/platform-express';
import { DataSource } from 'typeorm';
import { DatabaseHealth } from '../src/database/database.health.js';
import { createTestApp } from './app.js';
import { TEST_SCHEMA } from './setup.js';

/** 다른 서버들의 스키마. 게시판 서버의 계정은 여기에 들어갈 수 없어야 한다 */
const OTHER_SCHEMAS = ['auth', 'game', 'billing'];

describe('DB 연결', () => {
  let app: NestExpressApplication;
  let dataSource: DataSource;

  /** 값 하나를 돌려주는 쿼리를 보내고 그 값을 꺼낸다. */
  async function scalar<T>(
    sql: string,
    parameters: unknown[] = [],
  ): Promise<T> {
    const rows: { value: T }[] = await dataSource.query(sql, parameters);
    return rows[0].value;
  }

  beforeAll(async () => {
    app = await createTestApp();
    dataSource = app.get(DataSource);
  });

  afterAll(async () => {
    await app.close();
  });

  it('DB 가 답한다', async () => {
    await expect(app.get(DatabaseHealth).ping()).resolves.toBeUndefined();
  });

  it('테스트는 테스트용 스키마에서 돈다', async () => {
    const schema = await scalar<string>('SELECT current_schema() AS value');

    // 개발용 데이터(board 스키마)를 건드리지 않는다
    expect(schema).toBe(TEST_SCHEMA);
  });

  it('게시판 서버의 계정으로 접속한다', async () => {
    const user = await scalar<string>('SELECT current_user AS value');

    // 관리용 슈퍼유저로 접속하면, 권한 때문에 실패해야 할 코드가 통과한다
    expect(user).toBe('board');
  });

  it.each(OTHER_SCHEMAS)(
    '다른 서버의 스키마(%s)를 읽을 수 없다',
    async (schema) => {
      const canUse = await scalar<boolean>(
        "SELECT has_schema_privilege(current_user, $1, 'USAGE') AS value",
        [schema],
      );

      // 다른 서버의 테이블을 직접 읽지 않는다는 것을 약속이 아니라 DB 권한으로 지킨다
      expect(canUse).toBe(false);
    },
  );

  it.each(OTHER_SCHEMAS)(
    '다른 서버의 스키마(%s)에 테이블을 만들 수 없다',
    async (schema) => {
      const canCreate = await scalar<boolean>(
        "SELECT has_schema_privilege(current_user, $1, 'CREATE') AS value",
        [schema],
      );

      expect(canCreate).toBe(false);
    },
  );

  it.each(OTHER_SCHEMAS)(
    '스키마 이름을 붙여 불러도 다른 서버의 스키마(%s)에는 닿지 않는다',
    async (schema) => {
      // search_path 에 기대지 않는다. 이름을 직접 붙여도 권한에서 막혀야 한다.
      // 없는 테이블을 읽는다. 스키마에 들어갈 수 없으면 테이블을 찾기도 전에 권한 없음(42501)이 난다.
      // 들어갈 수 있으면 "그런 테이블이 없다"(42P01)가 나서 이 테스트가 실패한다. 어느 쪽이든 남는 것이 없다
      await expect(
        dataSource.query(`SELECT 1 FROM ${schema}.no_such_table`),
      ).rejects.toMatchObject({ driverError: { code: '42501' } });
    },
  );
});
