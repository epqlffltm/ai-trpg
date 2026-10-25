// web/apps/web/src/pages/board/Board.test.tsx
// 공지·게시판(A11)의 읽기. 로그인 없이 머리에서 게시판으로(첫 게시판으로 보냄), 고정한 글과 쪽 넘기기,
// 글과 댓글(답글, 지운 댓글, 탈퇴한 글쓴이, 더 보기), 없는 글, 검색(규칙, 게시판 안과 모든 게시판, 503). 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/errors';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { boardProblemText } from './boardProblem';
import { authorName, commentText, normalizeQuery, pageCount, parsePage, searchHint, searchPath } from './boardView';

const BOARD = '/api/v1/board';
const AT = '2026-10-24T03:00:00.000Z';
const BOARDS = [
  { slug: 'notice', name: '공지사항', description: '운영 소식', write_policy: 'operator' },
  { slug: 'free', name: '자유 게시판', description: '', write_policy: 'member' },
];

function post(id: string, title: string, extra: Record<string, unknown> = {}) {
  return { id, board: 'notice', title, author_id: 'u1', author_nickname: '운영자', author_withdrawn: false, comment_count: 0, pinned: false, pinned_until: null, created_at: AT, updated_at: AT, ...extra };
}

function comment(id: string, extra: Record<string, unknown> = {}) {
  return { id, post_id: '12', parent_id: null, author_id: 'u2', author_nickname: '모험가', author_withdrawn: false, content: `댓글 ${id}`, deleted: false, created_at: AT, updated_at: AT, ...extra };
}

function query(request: SeenRequest): URLSearchParams {
  return new URL(request.url, 'http://x').searchParams;
}

function signedOut(routes: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
    [`GET ${BOARD}/boards`]: () => json(200, BOARDS),
    [`GET ${BOARD}/boards/notice/posts`]: (request) =>
      query(request).get('page') === '2'
        ? json(200, { pinned: [], items: [post('3', '지난 점검')], page: 2, size: 20, total: 21 })
        : json(200, { pinned: [post('9', '이용 안내', { pinned: true, pinned_until: AT })], items: [post('12', '11월 점검', { comment_count: 3 })], page: 1, size: 20, total: 21 }),
    ...routes,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('게시판 읽기', () => {
  it('로그인하지 않아도 머리에서 첫 게시판으로 가고, 고정한 글을 위에 두고, 쪽을 넘긴다', async () => {
    const { seen } = signedOut();
    renderApp('/');

    await userEvent.click(await screen.findByRole('link', { name: '게시판' }));
    expect(await screen.findByRole('heading', { name: '공지사항' })).toBeInTheDocument();
    expect(within(screen.getByRole('navigation', { name: '게시판' })).getByRole('link', { name: '공지사항' })).toHaveAttribute('aria-current', 'page');
    const pinned = within(await screen.findByRole('list', { name: '고정한 글' }));
    expect(pinned.getByText('고정')).toBeInTheDocument();
    expect(pinned.getByRole('link', { name: '이용 안내' })).toHaveAttribute('href', '/board/posts/9');
    expect(screen.getByLabelText('댓글 3개')).toBeInTheDocument();
    expect(screen.getByText('1 / 2쪽')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('link', { name: '다음' }));
    expect(await screen.findByRole('link', { name: '지난 점검' })).toBeInTheDocument();
    expect(screen.queryByRole('list', { name: '고정한 글' })).toBeNull();
    expect(seen.some((request) => request.url.endsWith('/boards/notice/posts?page=2&size=20'))).toBe(true);
  });

  it('글을 읽고, 답글과 지운 댓글, 탈퇴한 글쓴이를 보이고, 댓글을 더 받는다', async () => {
    const { seen } = signedOut({
      [`GET ${BOARD}/posts/12`]: () => json(200, { ...post('12', '11월 점검', { comment_count: 3, author_withdrawn: true, author_id: null, author_nickname: null }), content: '첫 줄\n둘째 줄' }),
      [`GET ${BOARD}/posts/12/comments`]: (request) =>
        query(request).get('after') === '20'
          ? json(200, { items: [{ ...comment('30'), replies: [] }], next: null })
          : json(200, {
              items: [{ ...comment('20', { deleted: true, content: null, author_id: null, author_nickname: null }), replies: [comment('21', { parent_id: '20', content: '답글이다' })] }],
              next: '20',
            }),
    });
    renderApp('/board/posts/12');

    expect(await screen.findByRole('heading', { name: '11월 점검' })).toBeInTheDocument();
    expect(screen.getByText(/탈퇴한 사용자/)).toBeInTheDocument();
    expect(screen.getByText(/첫 줄/)).toHaveTextContent('첫 줄 둘째 줄');
    expect(within(screen.getByRole('article', { name: '11월 점검' })).getByRole('link', { name: '공지사항' })).toHaveAttribute('href', '/board/notice');
    expect(await screen.findByText('삭제된 댓글입니다')).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: '답글' })).getByText('답글이다')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '댓글 더 보기' }));
    expect(await screen.findByText('댓글 30')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '댓글 더 보기' })).toBeNull();
    expect(seen.some((request) => request.url.includes('/comments?after=20&size=50'))).toBe(true);
  });

  it('없는 글이면 까닭과 게시판으로 가는 길', async () => {
    signedOut({ [`GET ${BOARD}/posts/99`]: () => json(404, { detail: 'x' }) });
    renderApp('/board/posts/99');
    expect(await screen.findByText(/없는 글이거나 지운 글입니다/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '게시판으로' })).toHaveAttribute('href', '/board');
  });
});

describe('글 검색', () => {
  it('규칙에 맞지 않으면 막고, 게시판 안에서 찾고, 모든 게시판으로 넓힌다. 3초를 넘기면 까닭을 적는다', async () => {
    let slow = false;
    const { seen } = signedOut({
      [`GET ${BOARD}/posts`]: (request) =>
        slow ? json(503, { detail: 'x' }) : json(200, { items: [post('12', '11월 점검', { board: query(request).get('board') ?? 'free' })], page: 1, size: 20, total: 1 }),
    });
    renderApp('/board/notice');

    const box = await screen.findByRole('textbox', { name: '검색어' });
    await userEvent.type(box, '점 검');
    expect(screen.getByText('낱말마다 2자 이상으로 적어 주세요.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '찾기' })).toBeDisabled();
    await userEvent.clear(box);
    await userEvent.type(box, ' 11월   점검 ');
    await userEvent.click(screen.getByRole('button', { name: '찾기' }));

    expect(await screen.findByRole('heading', { name: '글 검색' })).toBeInTheDocument();
    expect(screen.getByText(/찾는 곳: 공지사항/)).toBeInTheDocument();
    expect(await screen.findByText('찾은 글 1개')).toBeInTheDocument();
    const first = seen.find((request) => request.url.startsWith(`${BOARD}/posts?`));
    expect(query(first as SeenRequest).get('q')).toBe('11월 점검');
    expect(query(first as SeenRequest).get('board')).toBe('notice');

    await userEvent.click(screen.getByRole('link', { name: '모든 게시판에서 찾기' }));
    expect(await screen.findByText(/찾는 곳: 모든 게시판/)).toBeInTheDocument();
    expect(await screen.findByText('[자유 게시판]')).toBeInTheDocument();

    slow = true;
    await userEvent.clear(screen.getByRole('textbox', { name: '검색어' }));
    await userEvent.type(screen.getByRole('textbox', { name: '검색어' }), '느린 검색');
    await userEvent.click(screen.getByRole('button', { name: '찾기' }));
    expect(await screen.findByText(/검색이 오래 걸려 멈췄습니다/)).toBeInTheDocument();
  });
});

describe('게시판의 순수한 함수', () => {
  it('글쓴이, 지운 댓글, 쪽, 검색어', () => {
    expect(authorName({ author_nickname: null, author_withdrawn: false })).toBe('알 수 없음');
    expect(authorName({ author_nickname: '렌', author_withdrawn: false })).toBe('렌');
    expect(commentText({ deleted: true, content: null })).toBe('삭제된 댓글입니다');
    expect(parsePage('3')).toBe(3);
    expect(parsePage('0')).toBe(1);
    expect(parsePage('x')).toBe(1);
    expect(parsePage('99999')).toBe(10000);
    expect(pageCount(0, 20)).toBe(1);
    expect(pageCount(41, 20)).toBe(3);
    expect(normalizeQuery(' 고정  버그 고정 ')).toBe('고정 버그');
    expect(searchHint('')).toBeNull();
    expect(searchHint('가나 다라 마바 사아 자차 카타')).toBe('낱말은 5개까지입니다.');
    expect(searchHint('가'.repeat(51))).toBe('검색어는 50자까지입니다.');
    expect(searchPath('고정 버그', 'free')).toBe('/board/search?q=%EA%B3%A0%EC%A0%95+%EB%B2%84%EA%B7%B8&board=free');
    expect(boardProblemText(new ApiError({ status: 400, detail: 'x', fields: { q: ['검색어는 낱말마다 2자 이상이어야 합니다.'] }, body: { errors: { q: ['검색어는 낱말마다 2자 이상이어야 합니다.'] } } }), '검색')).toBe('검색어는 낱말마다 2자 이상이어야 합니다.');
    expect(boardProblemText(new ApiError({ status: 503, detail: 'x', retryAfter: 5 }), '글')).toContain('5초 뒤에');
  });
});
