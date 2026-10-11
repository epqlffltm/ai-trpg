// board-server/src/boards/board-slug.pipe.spec.ts

/**
 * 주소의 게시판 이름을 검사하는 파이프(board-slug.pipe.ts)를 검증한다.
 */

import { NotFoundException } from '@nestjs/common';
import { BoardSlugPipe, isBoardSlug } from './board-slug.pipe.js';

describe('isBoardSlug', () => {
  it.each(['free', 'notice', 'scenario-2', 'a', 'a'.repeat(30)])(
    '영문 소문자, 숫자, 붙임표(%j)는 게시판 이름이다',
    (value) => {
      expect(isBoardSlug(value)).toBe(true);
    },
  );

  it.each([
    '',
    'Free',
    '자유',
    'free board',
    'free/notice',
    "free' OR 1=1--",
    'free\u0000',
    'a'.repeat(31),
    42,
    undefined,
  ])('게시판 이름의 모양이 아니다(%j)', (value) => {
    expect(isBoardSlug(value)).toBe(false);
  });
});

describe('BoardSlugPipe', () => {
  it('게시판 이름을 그대로 돌려준다', () => {
    expect(new BoardSlugPipe().transform('free')).toBe('free');
  });

  it('게시판 이름의 모양이 아니면 그런 게시판이 없는 것이다', () => {
    expect(() => new BoardSlugPipe().transform('free\u0000')).toThrow(
      NotFoundException,
    );
  });
});
