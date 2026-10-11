// board-server/src/posts/search-posts.query.spec.ts

/**
 * 글을 검색할 때 받는 값의 규칙(search-posts.query.ts)을 검증한다.
 * 서버를 띄우지 않고, 앱이 쓰는 것과 같은 파이프에 값을 넣어 본다.
 */

import { BadRequestException } from '@nestjs/common';
import { validationPipe } from '../errors/validation.js';
import { DEFAULT_PAGE, DEFAULT_PAGE_SIZE } from './page.js';
import { SearchPostsQuery } from './search-posts.query.js';
import { MAX_QUERY_LENGTH } from './search.js';

/** 주소에 붙은 값을 규칙대로 검사한다. 통과하면 바뀐 값을 돌려준다. */
function check(value: unknown): Promise<SearchPostsQuery> {
  return validationPipe().transform(value, {
    type: 'query',
    metatype: SearchPostsQuery,
  });
}

/** 검사에 걸린 칸의 이름들. 통과하면 빈 목록이다. */
async function rejectedFields(value: unknown): Promise<string[]> {
  const failure = await check(value).then(
    () => undefined,
    (error: unknown) => error,
  );
  if (failure === undefined) {
    return [];
  }
  expect(failure).toBeInstanceOf(BadRequestException);
  const body = (failure as BadRequestException).getResponse() as {
    errors: Record<string, string[]>;
  };
  return Object.keys(body.errors);
}

describe('SearchPostsQuery', () => {
  it('검색어만 있으면 통과하고, 쪽은 기본값이다', async () => {
    const query = await check({ q: '공지' });

    expect(query.q).toBe('공지');
    expect(query.board).toBeUndefined();
    expect(query.page).toBe(DEFAULT_PAGE);
    expect(query.size).toBe(DEFAULT_PAGE_SIZE);
  });

  it('검색어의 앞뒤 빈칸을 떼고 이어진 빈칸을 줄인다', async () => {
    expect((await check({ q: '  고정 \t  버그 ' })).q).toBe('고정 버그');
  });

  it('게시판과 쪽을 함께 받는다', async () => {
    const query = await check({
      q: '공지',
      board: 'free',
      page: '2',
      size: '5',
    });

    expect(query).toMatchObject({ board: 'free', page: 2, size: 5 });
  });

  it.each([
    ['없다', {}],
    ['비었다', { q: '' }],
    ['빈칸뿐이다', { q: '   ' }],
    ['한 글자다', { q: '가' }],
    ['한 글자인 낱말이 섞였다', { q: '고정 가' }],
    ['낱말이 너무 많다', { q: '하나 두울 세엣 네엣 다섯 여섯' }],
    ['너무 길다', { q: '가'.repeat(MAX_QUERY_LENGTH + 1) }],
    ['NUL 이 들었다', { q: '고정\u0000버그' }],
    ['여러 번 적었다', { q: ['고정', '버그'] }],
  ])('검색어가 %s -> 거부한다', async (_name, value) => {
    expect(await rejectedFields(value)).toEqual(['q']);
  });

  it('가장 긴 검색어까지 받는다', async () => {
    const longest = '가'.repeat(MAX_QUERY_LENGTH);

    expect((await check({ q: longest })).q).toBe(longest);
  });

  it('LIKE 의 기호가 든 검색어도 받는다. 글자로 찾는다', async () => {
    expect((await check({ q: '100% snake_case' })).q).toBe('100% snake_case');
  });

  it.each(['Free', 'free board', 'a'.repeat(31), '', "free'--"])(
    '게시판 이름의 모양이 아니면(%j) 거부한다',
    async (board) => {
      expect(await rejectedFields({ q: '공지', board })).toEqual(['board']);
    },
  );

  it('쪽의 규칙은 글 목록과 같다', async () => {
    expect(await rejectedFields({ q: '공지', page: '0' })).toEqual(['page']);
    expect(await rejectedFields({ q: '공지', size: '51' })).toEqual(['size']);
  });

  it('모르는 값은 거부한다', async () => {
    expect(await rejectedFields({ q: '공지', sort: 'old' })).toEqual(['sort']);
  });
});
