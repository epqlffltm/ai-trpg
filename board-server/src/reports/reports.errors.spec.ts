// board-server/src/reports/reports.errors.spec.ts

/**
 * 신고의 오류 응답과 DB 오류의 판정(reports.errors.ts)을 검증한다.
 */

import { QueryFailedError } from 'typeorm';
import { cannotReportOwn, isUniqueViolation } from './reports.errors.js';

/** DB 가 이 번호의 오류를 낸 것처럼 만든다. */
function queryFailed(code: string): QueryFailedError {
  const driverError = Object.assign(new Error('db'), { code });
  return new QueryFailedError('INSERT', [], driverError);
}

describe('isUniqueViolation', () => {
  it('23505 는 유일 제약에 걸린 것이다', () => {
    expect(isUniqueViolation(queryFailed('23505'))).toBe(true);
  });

  it.each([
    ['다른 DB 오류', queryFailed('23503')],
    ['DB 의 오류가 아닌 것', new Error('23505')],
    ['오류가 아닌 값', '23505'],
  ])('%s 는 아니다', (_, error) => {
    expect(isUniqueViolation(error)).toBe(false);
  });
});

describe('cannotReportOwn', () => {
  it('글과 댓글의 문장이 다르다', () => {
    expect(cannotReportOwn('post').getResponse()).toEqual({
      detail: '자신의 글은 신고할 수 없습니다.',
    });
    expect(cannotReportOwn('comment').getResponse()).toEqual({
      detail: '자신의 댓글은 신고할 수 없습니다.',
    });
  });
});
