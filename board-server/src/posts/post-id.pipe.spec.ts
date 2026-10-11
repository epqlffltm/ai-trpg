// board-server/src/posts/post-id.pipe.spec.ts

/**
 * 주소의 글 번호를 검사하는 파이프(post-id.pipe.ts)를 검증한다.
 * 번호의 모양 자체는 src/ids/record-id.spec.ts 가 본다.
 */

import { NotFoundException } from '@nestjs/common';
import { PostIdPipe } from './post-id.pipe.js';

describe('PostIdPipe', () => {
  it('글 번호를 글자 그대로 돌려준다', () => {
    expect(new PostIdPipe().transform('1234')).toBe('1234');
  });

  it.each(['abc', '0', '-1', undefined])(
    '글 번호의 모양이 아니면(%j) 그런 글이 없는 것이다',
    (value) => {
      expect(() => new PostIdPipe().transform(value)).toThrow(
        NotFoundException,
      );
    },
  );
});
