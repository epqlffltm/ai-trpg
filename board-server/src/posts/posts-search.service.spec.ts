// board-server/src/posts/posts-search.service.spec.ts

/**
 * 글 검색 서비스의 순수한 함수(posts-search.service.ts 의 isStatementTimeout)를 검증한다.
 * DB 를 쓰는 일은 test/search.e2e-spec.ts 와 test/search-timeout.e2e-spec.ts 가 실제 PostgreSQL 에서 본다.
 */

import { QueryFailedError } from 'typeorm';
import { isStatementTimeout } from './posts-search.service.js';

/** DB 가 낸 오류를 TypeORM 이 감싼 모양으로 만든다. */
function queryFailed(code: string): QueryFailedError {
  const driverError = Object.assign(new Error('db error'), { code });
  return new QueryFailedError('SELECT 1', [], driverError);
}

describe('isStatementTimeout', () => {
  it('DB 가 시간 제한으로 쿼리를 멈춘 오류를 가린다', () => {
    expect(isStatementTimeout(queryFailed('57014'))).toBe(true);
  });

  it('DB 의 다른 오류는 아니다', () => {
    // 23505: 유일해야 하는 값이 겹쳤다
    expect(isStatementTimeout(queryFailed('23505'))).toBe(false);
  });

  it.each([new Error('57014'), '57014', null, undefined, { code: '57014' }])(
    'DB 의 오류가 아닌 것(%j)은 아니다',
    (error) => {
      expect(isStatementTimeout(error)).toBe(false);
    },
  );
});
