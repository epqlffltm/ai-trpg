// board-server/src/ids/record-id.spec.ts

/**
 * 번호의 모양을 가리는 함수(record-id.ts)를 검증한다.
 */

import { isRecordId } from './record-id.js';

describe('isRecordId', () => {
  it.each(['1', '42', '1234567890', '999999999999999999'])(
    '1 이상의 정수(%j)는 번호다',
    (value) => {
      expect(isRecordId(value)).toBe(true);
    },
  );

  it.each([
    '',
    '0',
    '01',
    '-1',
    '1.5',
    '1e3',
    'abc',
    '12a',
    ' 12',
    '0x10',
    // DB 의 bigint 에 들어가지 않는 크기
    '9999999999999999999',
    '99999999999999999999999',
    12,
    undefined,
    null,
  ])('번호의 모양이 아니다(%j)', (value) => {
    expect(isRecordId(value)).toBe(false);
  });
});
