// web/apps/web/src/pages/board/BoardWrite.test.tsx
// 공지·게시판(A11)의 쓰기. 글쓰기(폼 검사, 서버의 칸 문장, 운영자 게시판), 고치기(바뀐 칸만), 지우기(한 번 더 묻기),
// 신고(사유, 기타의 설명, 이미 신고함), 댓글과 답글과 고치기, 너무 자주(429), 운영자의 고정과 풀기, 로그인 전의 길.
// 누구에게 어떤 단추를 보일지, 폼의 검사와 본문, 실패의 문장을 짓는 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, NetworkError } from '../../api/errors';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';
import { commentProblem, parsePinDays, postBody, postDraftProblems, postPatch, reportBody, reportDraftProblems } from './boardForm';
import { canDeleteComment, canDeletePost, canEditComment, canEditPost, canPin, canReply, canReport, canWritePost } from './boardPermissions';
import { describeBoardWriteProblem } from './boardWriteProblem';

const BOARD = '/api/v1/board';
const AT = '2026-10-24T03:00:00.000Z';
const OTHER = '00000000-0000-4000-8000-0000000000b2';
const BOARDS = [
  { slug: 'notice', name: '공지사항', description: '', write_policy: 'operator' },
  { slug: 'free', name: '자유 게시판', description: '', write_policy: 'member' },
];

type Row = Record<string, unknown>;

function post(id: string, extra: Row = {}): Row {
  return { id, board: 'free', title: `글 ${id}`, content: `본문 ${id}`, author_id: ME, author_nickname: '모험가', author_withdrawn: false, comment_count: 0, pinned: false, pinned_until: null, created_at: AT, updated_at: AT, ...extra };
}

function comment(id: string, extra: Row = {}): Row {
  return { id, post_id: '7', parent_id: null, author_id: OTHER, author_nickname: '길손', author_withdrawn: false, content: `댓글 ${id}`, deleted: false, created_at: AT, updated_at: AT, ...extra };
}

function account() {
  return {
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () =>
      json(200, { nickname: '모험가', public_id: ME, username: 'p', email: 'e@x', identity: { verified: true, legal_adult: true, adult_content: true }, guardian_consent: 'none', consents_pending: [], withdrawal_scheduled_at: null }),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/notification/me/notifications/unread-count': () => json(200, { unread: 0 }),
  };
}

/** 글 7(내 글이거나 남의 글)과 댓글. 쓰고 고친 것이 다시 읽을 때 보이도록 상태를 둔다 */
function board(options: { operator?: boolean; postAuthor?: string; routes?: Record<string, (request: SeenRequest) => Response> } = {}) {
  let current = post('7', { author_id: options.postAuthor ?? ME });
  let threads: Row[] = [{ ...comment('20'), replies: [] }, { ...comment('30', { author_id: ME, author_nickname: '모험가' }), replies: [] }];
  return installFakeFetch({
    ...account(),
    [`GET ${BOARD}/me`]: () => json(200, { user_id: ME, is_operator: options.operator ?? false }),
    [`GET ${BOARD}/boards`]: () => json(200, BOARDS),
    [`GET ${BOARD}/boards/free/posts`]: () => json(200, { pinned: [], items: [current], page: 1, size: 20, total: 1 }),
    [`GET ${BOARD}/boards/notice/posts`]: () => json(200, { pinned: [], items: [], page: 1, size: 20, total: 0 }),
    [`GET ${BOARD}/posts/7`]: () => json(200, current),
    [`GET ${BOARD}/posts/7/comments`]: () => json(200, { items: threads, next: null }),
    [`PATCH ${BOARD}/posts/7`]: (request) => {
      current = { ...current, ...(request.body as Row), updated_at: '2026-10-25T00:00:00.000Z' };
      return json(200, current);
    },
    [`DELETE ${BOARD}/posts/7`]: () => new Response(null, { status: 204 }),
    [`PUT ${BOARD}/posts/7/pin`]: () => {
      current = { ...current, pinned: true, pinned_until: '2026-11-01T03:00:00.000Z' };
      return new Response(null, { status: 204 });
    },
    [`DELETE ${BOARD}/posts/7/pin`]: () => {
      current = { ...current, pinned: false, pinned_until: null };
      return new Response(null, { status: 204 });
    },
    [`POST ${BOARD}/posts/7/comments`]: (request) => {
      const body = request.body as { content: string; parent_id: string | null };
      const made = comment(String(40 + threads.length), { author_id: ME, author_nickname: '모험가', content: body.content, parent_id: body.parent_id });
      threads = body.parent_id === null ? [...threads, { ...made, replies: [] }] : threads.map((thread) => (thread.id === body.parent_id ? { ...thread, replies: [...(thread.replies as Row[]), made] } : thread));
      current = { ...current, comment_count: Number(current.comment_count) + 1 };
      return json(201, made);
    },
    [`PATCH ${BOARD}/comments/30`]: (request) => {
      threads = threads.map((thread) => (thread.id === '30' ? { ...thread, content: (request.body as Row).content, updated_at: '2026-10-25T00:00:00.000Z' } : thread));
      return json(200, threads[1]);
    },
    ...options.routes,
  });
}

function sent(seen: SeenRequest[], method: string, path: string): unknown[] {
  return seen.filter((request) => request.method === method && request.url === `${BOARD}${path}`).map((request) => request.body);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('글쓰기', () => {
  it('누구나 쓰는 게시판에서 글을 쓴다. 빈 칸은 보내지 않고, 서버의 칸 문장을 칸 옆에 보이고, 올리면 그 글로 간다', async () => {
    let tries = 0;
    const { seen } = board({
      routes: {
        [`POST ${BOARD}/boards/free/posts`]: (request) => {
          tries += 1;
          if (tries === 1) return json(400, { detail: '입력이 올바르지 않습니다.', errors: { title: ['제목에 쓸 수 없는 글자가 있습니다.'] } });
          return json(201, post('7', { ...(request.body as Row) }));
        },
      },
    });
    renderApp('/board/free');

    await userEvent.click(await screen.findByRole('link', { name: '글쓰기' }));
    expect(await screen.findByRole('heading', { name: '글쓰기' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '올리기' }));
    expect(screen.getByText('제목을 적어 주세요.')).toBeInTheDocument();
    expect(screen.getByText('본문을 적어 주세요.')).toBeInTheDocument();
    expect(sent(seen, 'POST', '/boards/free/posts')).toEqual([]);

    await userEvent.type(screen.getByLabelText('제목'), '  첫 모험  ');
    await userEvent.type(screen.getByLabelText('본문'), '함께 갈 사람');
    await userEvent.click(screen.getByRole('button', { name: '올리기' }));
    expect(await screen.findByText('제목에 쓸 수 없는 글자가 있습니다.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '올리기' }));
    expect(await screen.findByRole('heading', { name: '첫 모험' })).toBeInTheDocument();
    expect(sent(seen, 'POST', '/boards/free/posts')).toEqual([
      { title: '첫 모험', content: '함께 갈 사람' },
      { title: '첫 모험', content: '함께 갈 사람' },
    ]);
  });

  it('운영자만 쓰는 게시판은 운영자가 아니면 글쓰기를 보이지 않고, 주소로 와도 까닭을 보인다', async () => {
    board();
    renderApp('/board/notice');
    expect(await screen.findByText('아직 글이 없습니다.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '글쓰기' })).toBeNull();
  });

  it('운영자 게시판의 글쓰기 주소로 오면 폼 대신 까닭을 보인다', async () => {
    board();
    renderApp('/board/notice/new');
    expect(await screen.findByText('이 게시판에는 운영자만 글을 씁니다.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '올리기' })).toBeNull();
  });

  it('운영자에게는 운영자 게시판에도 글쓰기와 첫 글 안내가 보인다', async () => {
    board({ operator: true });
    renderApp('/board/notice');
    expect(await screen.findByRole('link', { name: '글쓰기' })).toHaveAttribute('href', '/board/notice/new');
    expect(await screen.findByText('아직 글이 없습니다. 첫 글을 써 보세요.')).toBeInTheDocument();
  });

  it('글을 너무 자주 쓰면 남은 초를 보인다', async () => {
    board({ routes: { [`POST ${BOARD}/boards/free/posts`]: () => json(429, { detail: '글을 너무 자주 쓰고 있습니다.', retry_after: 142 }, { 'Retry-After': '142' }) } });
    renderApp('/board/free/new');
    await userEvent.type(await screen.findByLabelText('제목'), '제목');
    await userEvent.type(screen.getByLabelText('본문'), '본문');
    await userEvent.click(screen.getByRole('button', { name: '올리기' }));
    expect(await screen.findByText('글을 너무 자주 썼습니다. 142초 뒤에 다시 해 주세요.')).toBeInTheDocument();
  });
});

describe('내 글과 남의 글', () => {
  it('내 글은 바뀐 칸만 보내 고치고, 한 번 더 물은 뒤 지우면 게시판으로 간다. 내 글에는 신고가 없다', async () => {
    const { seen } = board();
    renderApp('/board/posts/7');

    expect(await screen.findByRole('heading', { name: '글 7' })).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: '고치기' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '글 신고' })).toBeNull();
    expect(screen.queryByRole('button', { name: '고정' })).toBeNull();

    await userEvent.click(screen.getByRole('link', { name: '고치기' }));
    const title = await screen.findByLabelText('제목');
    expect(title).toHaveValue('글 7');
    await userEvent.clear(title);
    await userEvent.type(title, '고친 제목');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByRole('heading', { name: '고친 제목' })).toBeInTheDocument();
    expect(sent(seen, 'PATCH', '/posts/7')).toEqual([{ title: '고친 제목' }]);

    await userEvent.click(screen.getByRole('button', { name: '글 지우기' }));
    await userEvent.click(within(screen.getByRole('dialog', { name: '글 지우기' })).getByRole('button', { name: '지우기' }));
    expect(await screen.findByRole('heading', { name: '자유 게시판' })).toBeInTheDocument();
    expect(seen.filter((request) => request.method === 'DELETE' && request.url === `${BOARD}/posts/7`)).toHaveLength(1);
  });

  it('고친 것이 없으면 보내지 않고 글로 돌아간다', async () => {
    const { seen } = board();
    renderApp('/board/posts/7/edit');
    await userEvent.click(await screen.findByRole('button', { name: '저장' }));
    expect(await screen.findByRole('heading', { name: '글 7' })).toBeInTheDocument();
    expect(sent(seen, 'PATCH', '/posts/7')).toEqual([]);
  });

  it('남의 글은 고치지 못하고(주소로 와도), 신고한다. 기타는 설명을 받고, 접수를 알리고, 이미 신고했으면 서버의 문장을 보인다', async () => {
    let reports = 0;
    const { seen } = board({
      postAuthor: OTHER,
      routes: {
        [`POST ${BOARD}/posts/7/reports`]: () => {
          reports += 1;
          return reports === 1 ? json(201, { id: '1', reason: 'other', created_at: AT }) : json(409, { detail: '이미 신고했습니다.' });
        },
      },
    });
    renderApp('/board/posts/7');

    const report = await screen.findByRole('button', { name: '글 신고' });
    expect(screen.queryByRole('link', { name: '고치기' })).toBeNull();
    expect(screen.queryByRole('button', { name: '글 지우기' })).toBeNull();

    await userEvent.click(report);
    let dialog = within(screen.getByRole('dialog', { name: '글 신고' }));
    await userEvent.click(dialog.getByRole('button', { name: '신고하기' }));
    expect(dialog.getByText('사유를 골라 주세요.')).toBeInTheDocument();
    await userEvent.click(dialog.getByLabelText('기타(설명을 꼭 적어 주세요)'));
    await userEvent.click(dialog.getByRole('button', { name: '신고하기' }));
    expect(dialog.getByText('기타는 설명을 적어 주세요.')).toBeInTheDocument();
    await userEvent.type(dialog.getByLabelText('설명'), '같은 글을 여러 번 올림');
    await userEvent.click(dialog.getByRole('button', { name: '신고하기' }));
    expect(await dialog.findByText('신고를 접수했습니다. 운영자가 살펴봅니다.')).toBeInTheDocument();
    expect(sent(seen, 'POST', '/posts/7/reports')).toEqual([{ reason: 'other', description: '같은 글을 여러 번 올림' }]);

    await userEvent.click(dialog.getByRole('button', { name: '닫기' }));
    await userEvent.click(screen.getByRole('button', { name: '글 신고' }));
    dialog = within(screen.getByRole('dialog', { name: '글 신고' }));
    await userEvent.click(dialog.getByLabelText('스팸, 광고'));
    await userEvent.click(dialog.getByRole('button', { name: '신고하기' }));
    expect(await dialog.findByText('이미 신고했습니다.')).toBeInTheDocument();
    expect(sent(seen, 'POST', '/posts/7/reports')[1]).toEqual({ reason: 'spam' });
  });

  it('남의 글의 고치기 주소로 오면 까닭을 보인다', async () => {
    board({ postAuthor: OTHER });
    renderApp('/board/posts/7/edit');
    expect(await screen.findByText('자신의 글만 고칠 수 있습니다.')).toBeInTheDocument();
    expect(screen.queryByLabelText('제목')).toBeNull();
  });
});

describe('댓글', () => {
  it('댓글을 달고, 남의 댓글에 답글을 달고, 내 댓글을 고친다. 남의 댓글만 신고한다', async () => {
    const { seen } = board();
    renderApp('/board/posts/7');

    await userEvent.type(await screen.findByLabelText('댓글 쓰기'), '저도 갑니다');
    await userEvent.click(screen.getByRole('button', { name: '댓글 달기' }));
    expect(await screen.findByText('저도 갑니다')).toBeInTheDocument();
    expect(screen.getByLabelText('댓글 쓰기')).toHaveValue('');
    expect(await screen.findByRole('heading', { name: '댓글 1개' })).toBeInTheDocument();

    expect(screen.getByRole('button', { name: '길손의 댓글 신고' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '모험가의 댓글 신고' })).toBeNull();
    expect(screen.queryByRole('button', { name: '길손의 댓글 지우기' })).toBeNull();

    await userEvent.click(screen.getByRole('button', { name: '길손의 댓글에 답글' }));
    await userEvent.type(screen.getByLabelText('답글 쓰기'), '반갑습니다');
    await userEvent.click(screen.getByRole('button', { name: '답글 달기' }));
    const replies = within(await screen.findByRole('list', { name: '답글' }));
    expect(replies.getByText('반갑습니다')).toBeInTheDocument();
    expect(replies.queryByRole('button', { name: /에 답글$/ })).toBeNull();
    expect(screen.queryByLabelText('답글 쓰기')).toBeNull();

    const mine = screen.getByText('댓글 30').closest('article') as HTMLElement;
    await userEvent.click(within(mine).getByRole('button', { name: '내 댓글 고치기' }));
    const editor = screen.getByLabelText('댓글 고치기');
    expect(editor).toHaveValue('댓글 30');
    await userEvent.clear(editor);
    await userEvent.type(editor, '고친 댓글');
    await userEvent.click(screen.getByRole('button', { name: '저장' }));
    expect(await screen.findByText('고친 댓글')).toBeInTheDocument();

    expect(sent(seen, 'POST', '/posts/7/comments')).toEqual([
      { content: '저도 갑니다', parent_id: null },
      { content: '반갑습니다', parent_id: '20' },
    ]);
    expect(sent(seen, 'PATCH', '/comments/30')).toEqual([{ content: '고친 댓글' }]);
  });

  it('운영자는 남의 댓글도 지운다. 답글이 다 찼으면 서버의 문장을 보인다', async () => {
    const { seen } = board({
      operator: true,
      routes: {
        [`DELETE ${BOARD}/comments/20`]: () => new Response(null, { status: 204 }),
        [`POST ${BOARD}/posts/7/comments`]: () => json(409, { detail: '이 댓글에는 답글을 더 달 수 없습니다.' }),
      },
    });
    renderApp('/board/posts/7');

    await userEvent.click(await screen.findByRole('button', { name: '길손의 댓글에 답글' }));
    await userEvent.type(screen.getByLabelText('답글 쓰기'), '하나 더');
    await userEvent.click(screen.getByRole('button', { name: '답글 달기' }));
    expect(await screen.findByText('이 댓글에는 답글을 더 달 수 없습니다.')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '그만두기' }));

    await userEvent.click(screen.getByRole('button', { name: '길손의 댓글 지우기' }));
    await userEvent.click(within(screen.getByRole('dialog', { name: '댓글 지우기' })).getByRole('button', { name: '지우기' }));
    await waitFor(() => expect(screen.queryByRole('dialog', { name: '댓글 지우기' })).toBeNull());
    expect(seen.filter((request) => request.method === 'DELETE' && request.url === `${BOARD}/comments/20`)).toHaveLength(1);
  });
});

describe('운영자의 고정', () => {
  it('날 수를 정해 고정하고, 끝나는 때를 보이고, 푼다', async () => {
    const { seen } = board({ operator: true, postAuthor: OTHER });
    renderApp('/board/posts/7');

    await userEvent.click(await screen.findByRole('button', { name: '고정' }));
    const dialog = within(screen.getByRole('dialog', { name: '글 고정' }));
    const days = dialog.getByLabelText('며칠 동안');
    expect(days).toHaveValue(7);
    await userEvent.clear(days);
    await userEvent.type(days, '400');
    await userEvent.click(dialog.getByRole('button', { name: '고정하기' }));
    expect(dialog.getByText('1일부터 365일까지 적어 주세요.')).toBeInTheDocument();
    await userEvent.clear(days);
    await userEvent.type(days, '3');
    await userEvent.click(dialog.getByRole('button', { name: '고정하기' }));

    expect(await screen.findByRole('button', { name: '고정 풀기' })).toBeInTheDocument();
    expect(screen.getByText(/까지 고정$/)).toBeInTheDocument();
    expect(sent(seen, 'PUT', '/posts/7/pin')).toEqual([{ days: 3 }]);

    await userEvent.click(screen.getByRole('button', { name: '고정 풀기' }));
    expect(await screen.findByRole('button', { name: '고정' })).toBeInTheDocument();
    expect(seen.filter((request) => request.method === 'DELETE' && request.url === `${BOARD}/posts/7/pin`)).toHaveLength(1);
  });
});

describe('로그인 전', () => {
  it('누구나 쓰는 게시판의 글쓰기는 로그인으로 보내고, 글에는 댓글 쓰기 대신 로그인으로 가는 길만 있다', async () => {
    installFakeFetch({
      [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }),
      [`GET ${BOARD}/boards`]: () => json(200, BOARDS),
      [`GET ${BOARD}/boards/free/posts`]: () => json(200, { pinned: [], items: [], page: 1, size: 20, total: 0 }),
      [`GET ${BOARD}/posts/7`]: () => json(200, post('7', { author_id: OTHER })),
      [`GET ${BOARD}/posts/7/comments`]: () => json(200, { items: [{ ...comment('20'), replies: [] }], next: null }),
    });
    renderApp('/board/posts/7');

    expect(await screen.findByText('댓글 20')).toBeInTheDocument();
    expect(within(screen.getByRole('region', { name: '댓글 0개' })).getByRole('link', { name: '로그인' })).toHaveAttribute('href', '/login');
    expect(screen.queryByLabelText('댓글 쓰기')).toBeNull();
    expect(screen.queryByRole('button', { name: '글 신고' })).toBeNull();
    expect(screen.queryByRole('button', { name: '길손의 댓글에 답글' })).toBeNull();

    await userEvent.click(screen.getAllByRole('link', { name: '자유 게시판' })[0] as HTMLElement);
    await userEvent.click(await screen.findByRole('link', { name: '글쓰기' }));
    expect(await screen.findByRole('heading', { name: '로그인' })).toBeInTheDocument();
  });
});

describe('순수한 함수', () => {
  const me = { user_id: ME, is_operator: false };
  const operator = { user_id: OTHER, is_operator: true };
  const free = { write_policy: 'member' as const };
  const notice = { write_policy: 'operator' as const };

  it('누구에게 어떤 단추를 보일지', () => {
    expect(canWritePost(free, undefined)).toBe(true);
    expect(canWritePost(notice, me)).toBe(false);
    expect(canWritePost(notice, operator)).toBe(true);
    expect(canWritePost(undefined, operator)).toBe(false);

    expect(canEditPost({ author_id: ME }, free, me)).toBe(true);
    expect(canEditPost({ author_id: ME }, free, operator)).toBe(false);
    expect(canEditPost({ author_id: ME }, notice, me)).toBe(false);
    expect(canEditPost({ author_id: null }, free, me)).toBe(false);
    expect(canDeletePost({ author_id: OTHER }, free, operator)).toBe(true);
    expect(canDeletePost({ author_id: ME }, notice, me)).toBe(false);
    expect(canDeletePost({ author_id: ME }, free, undefined)).toBe(false);
    expect(canPin(operator)).toBe(true);
    expect(canPin(me)).toBe(false);

    expect(canEditComment({ author_id: ME, deleted: false }, me)).toBe(true);
    expect(canEditComment({ author_id: null, deleted: true }, me)).toBe(false);
    expect(canDeleteComment({ author_id: ME, deleted: false }, operator)).toBe(true);
    expect(canDeleteComment({ author_id: OTHER, deleted: false }, me)).toBe(false);
    expect(canReport({ author_id: OTHER }, me)).toBe(true);
    expect(canReport({ author_id: null }, me)).toBe(true);
    expect(canReport({ author_id: ME }, me)).toBe(false);
    expect(canReport({ author_id: null, deleted: true }, me)).toBe(false);
    expect(canReport({ author_id: OTHER }, undefined)).toBe(false);
    expect(canReply({ parent_id: null, deleted: false })).toBe(true);
    expect(canReply({ parent_id: '1', deleted: false })).toBe(false);
    expect(canReply({ parent_id: null, deleted: true })).toBe(false);
  });

  it('글, 댓글, 신고, 고정의 검사와 본문', () => {
    expect(postDraftProblems({ title: '   ', content: '' })).toEqual({ title: '제목을 적어 주세요.', content: '본문을 적어 주세요.' });
    expect(postDraftProblems({ title: 'a'.repeat(101), content: 'b'.repeat(20_001) })).toEqual({ title: '제목은 100자까지입니다.', content: '본문은 20,000자까지입니다.' });
    expect(postDraftProblems({ title: ` ${'a'.repeat(100)} `, content: ' x ' })).toEqual({});
    expect(postBody({ title: ' 제목 ', content: ' 본문 ' })).toEqual({ title: '제목', content: ' 본문 ' });
    expect(postPatch({ title: '가', content: '나' }, { title: ' 가 ', content: '나' })).toBeNull();
    expect(postPatch({ title: '가', content: '나' }, { title: '가', content: '다' })).toEqual({ content: '다' });

    expect(commentProblem(' \n ')).toBe('내용을 적어 주세요.');
    expect(commentProblem('a'.repeat(2_001))).toBe('댓글은 2,000자까지입니다.');
    expect(commentProblem('좋아요')).toBeNull();

    expect(reportDraftProblems({ reason: '', description: '' })).toEqual({ reason: '사유를 골라 주세요.' });
    expect(reportDraftProblems({ reason: 'other', description: ' ' })).toEqual({ description: '기타는 설명을 적어 주세요.' });
    expect(reportDraftProblems({ reason: 'spam', description: 'a'.repeat(501) })).toEqual({ description: '설명은 500자까지입니다.' });
    expect(reportBody({ reason: 'spam', description: '  ' })).toEqual({ reason: 'spam' });
    expect(reportBody({ reason: 'abuse', description: '욕설' })).toEqual({ reason: 'abuse', description: '욕설' });
    expect(reportBody({ reason: '', description: '' })).toBeNull();

    expect(parsePinDays('7')).toBe(7);
    expect(parsePinDays('0')).toBeNull();
    expect(parsePinDays('366')).toBeNull();
    expect(parsePinDays('1.5')).toBeNull();
    expect(parsePinDays('')).toBeNull();
  });

  it('하지 못한 까닭의 문장', () => {
    expect(describeBoardWriteProblem(new ApiError({ status: 429, detail: 'x', retryAfter: 30 }), '신고')).toEqual({ message: '신고를 너무 자주 했습니다. 30초 뒤에 다시 해 주세요.', waitSeconds: 30 });
    expect(describeBoardWriteProblem(new ApiError({ status: 403, detail: '이 게시판에는 운영자만 글을 쓸 수 있습니다.' }), '글').message).toBe('이 게시판에는 운영자만 글을 쓸 수 있습니다.');
    expect(describeBoardWriteProblem(new ApiError({ status: 401, detail: 'x' }), '댓글').message).toBe('로그인이 끝났습니다. 다시 로그인한 뒤에 해 주세요.');
    expect(describeBoardWriteProblem(new ApiError({ status: 400, detail: 'x', fields: { content: ['내용이 너무 깁니다.'] }, body: { errors: {} } }), '댓글')).toEqual({ message: '적은 것을 확인해 주세요.', fields: { content: '내용이 너무 깁니다.' } });
    expect(describeBoardWriteProblem(new ApiError({ status: 500, detail: 'x', requestId: 'r1' }), '글')).toEqual({ message: '처리하지 못했습니다. 잠시 뒤에 다시 시도하세요.', requestId: 'r1' });
    expect(describeBoardWriteProblem(new NetworkError(new Error('down')), '글').message).toBe('서버에 닿지 못했습니다. 잠시 뒤에 다시 시도하세요.');
  });
});
