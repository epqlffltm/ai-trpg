// board-server/src/posts/post-id.pipe.spec.ts

/**
 * 주소의 글 번호를 검사하는 파이프(post-id.pipe.ts)를 검증한다.
 */

import { NotFoundException } from '@nestjs/common';
import { isPostId, PostIdPipe } from './post-id.pipe.js';

describe('isPostId', () => {
  it.each(['1', '42', '1234567890', '999999999999999999'])(
    '1 이상의 정수(%j)는 글 번호다',
    (value) => {
      expect(isPostId(value)).toBe(true);
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
  ])('글 번호의 모양이 아니다(%j)', (value) => {
    expect(isPostId(value)).toBe(false);
  });
});

describe('PostIdPipe', () => {
  it('글 번호를 글자 그대로 돌려준다', () => {
    expect(new PostIdPipe().transform('1234')).toBe('1234');
  });

  it('글 번호의 모양이 아니면 그런 글이 없는 것이다', () => {
    expect(() => new PostIdPipe().transform('abc')).toThrow(NotFoundException);
  });
});
