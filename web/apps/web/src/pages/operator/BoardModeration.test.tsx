// web/apps/web/src/pages/operator/BoardModeration.test.tsx
// 게시판의 신고 처리(E4, board). 운영자가 아니면 부르지 않는다. 운영자는 글과 댓글마다 묶은 줄(사유의 수, 지움 표, 글 보기)을 보고,
// 펼쳐 신고 하나하나(설명, 신고한 사람, 처리한 것)를 읽고 닫는다. 이미 닫혔으면(404) 알리고 목록을 다시 읽는다. 쪽을 이어 읽는다. 순수한 함수.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { boardOutcomeLabel, boardReasonLabel, boardReasonSummary, targetLabel, targetPostPath } from './boardReportView';
import { nextPage } from './moderationPure';

const BOARD = '/api/v1/board';
const AT = '2026-10-24T03:00:00.000Z';
const REPORTER = '00000000-0000-4000-8000-0000000000d1';

function base64Url(text: string): string {
  const bytes = new TextEncoder().encode(text);
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

function accessToken(roles: string[]): string {
  return `${base64Url('{"alg":"RS256"}')}.${base64Url(JSON.stringify({ sub: 'u1', roles }))}.sig`;
}

const REASONS = { spam: 2, abuse: 0, sexual: 0, illegal: 0, other: 1 };

function group(type: 'post' | 'comment', id: string, extra: Record<string, unknown> = {}) {
  return { target: { type, id, post_id: type === 'post' ? id : '12', deleted: false, ...extra }, open_count: 3, reasons: REASONS, first_reported_at: AT, last_reported_at: AT };
}

const REPORTS = [
  { id: '9', reason: 'other', description: '같은 글을 계속 올림', reporter_id: REPORTER, created_at: AT, handled_at: null, handled_by: null, outcome: null },
  { id: '8', reason: 'spam', description: null, reporter_id: null, created_at: AT, handled_at: AT, handled_by: 'u1', outcome: 'dismissed' },
];

type Routes = Record<string, (request: SeenRequest) => Response>;

function signedInAs(roles: string[], routes: Routes = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens(accessToken(roles))),
    'GET /api/v1/auth/me': () => json(200, { nickname: '운영자', identity: { adult_content: false } }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    'GET /api/v1/asset/admin/character-reports': () => json(200, { items: [], total: 0 }),
    'GET /api/v1/chat/admin/message-reports': () => json(200, { items: [], total: 0 }),
    ...routes,
  });
}

function calls(seen: SeenRequest[], method: string, path: string): SeenRequest[] {
  return seen.filter((request) => request.method === method && request.url.split('?')[0] === `${BOARD}${path}`);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('게시판의 신고 처리', () => {
  it('운영자가 아니면 게시판의 신고를 부르지 않는다', async () => {
    const { seen } = signedInAs([]);
    renderApp('/operator/reports');
    expect(await screen.findByRole('heading', { name: '찾을 수 없습니다' })).toBeInTheDocument();
    expect(calls(seen, 'GET', '/reports')).toHaveLength(0);
  });

  it('묶은 줄을 보고, 펼쳐 신고를 읽고, 조치함으로 닫으면 그 줄이 빠진다', async () => {
    let open = [group('post', '12'), group('comment', '57', { deleted: true })];
    const { seen } = signedInAs(['operator'], {
      [`GET ${BOARD}/reports`]: () => json(200, { items: open, page: 1, size: 20, total: open.length }),
      [`GET ${BOARD}/posts/12/reports`]: () => json(200, { items: REPORTS, page: 1, size: 20, total: 2 }),
      [`PUT ${BOARD}/posts/12/reports/outcome`]: () => {
        open = open.filter((item) => item.target.type !== 'post');
        return new Response(null, { status: 204 });
      },
    });
    renderApp('/operator/reports');

    const list = within(await screen.findByRole('list', { name: '신고된 글과 댓글' }));
    const post = (await list.findByText('글 12')).closest('li') as HTMLElement;
    expect(within(post).getByText('스팸·광고 2 · 기타 1')).toBeInTheDocument();
    expect(within(post).getByRole('link', { name: '글 보기' })).toHaveAttribute('href', '/board/posts/12');
    const comment = list.getByText('글 12 의 댓글 57').closest('li') as HTMLElement;
    expect(within(comment).getByText('지움')).toBeInTheDocument();
    expect(within(comment).getByRole('link', { name: '글 보기' })).toHaveAttribute('href', '/board/posts/12');
    expect(screen.getByRole('heading', { name: '게시판의 신고 (2개)' })).toBeInTheDocument();

    await userEvent.click(within(post).getByText('신고 보기와 처리'));
    const reports = within(await within(post).findByRole('list', { name: '이 글이나 댓글의 신고' }));
    expect(reports.getByText('같은 글을 계속 올림')).toBeInTheDocument();
    expect(reports.getByText(new RegExp(`신고한 사람 ${REPORTER}`))).toBeInTheDocument();
    expect(reports.getByText(/신고한 사람 탈퇴함/)).toBeInTheDocument();
    expect(reports.getByText(/· 문제없음 · .+에 처리$/)).toBeInTheDocument();

    await userEvent.click(within(post).getByRole('button', { name: '조치함으로 닫기' }));
    await waitFor(() => expect(list.queryByText('글 12')).toBeNull());
    expect(list.getByText('글 12 의 댓글 57')).toBeInTheDocument();
    expect(calls(seen, 'PUT', '/posts/12/reports/outcome').map((request) => request.body)).toEqual([{ outcome: 'actioned' }]);
  });

  it('지운 글은 글 보기가 없다. 다른 운영자가 먼저 닫았으면(404) 알리고 목록을 다시 읽는다', async () => {
    let reads = 0;
    signedInAs(['operator'], {
      [`GET ${BOARD}/reports`]: () => {
        reads += 1;
        return json(200, { items: [group('post', '30', { deleted: true })], page: 1, size: 20, total: 1 });
      },
      [`GET ${BOARD}/posts/30/reports`]: () => json(200, { items: REPORTS.slice(0, 1), page: 1, size: 20, total: 1 }),
      [`PUT ${BOARD}/posts/30/reports/outcome`]: () => json(404, { detail: '처리할 신고가 없습니다.' }),
    });
    renderApp('/operator/reports');

    const item = (await screen.findByText('글 30')).closest('li') as HTMLElement;
    expect(within(item).queryByRole('link', { name: '글 보기' })).toBeNull();
    await userEvent.click(within(item).getByText('신고 보기와 처리'));
    await userEvent.click(await within(item).findByRole('button', { name: '문제없음으로 닫기' }));
    expect(await within(item).findByText('닫을 열린 신고가 없습니다. 다른 운영자가 먼저 닫았을 수 있습니다.')).toBeInTheDocument();
    await waitFor(() => expect(reads).toBe(2));
  });

  it('남은 쪽을 이어 읽는다', async () => {
    const { seen } = signedInAs(['operator'], {
      [`GET ${BOARD}/reports`]: (request) =>
        new URL(request.url, 'http://x').searchParams.get('page') === '2'
          ? json(200, { items: [group('post', '99')], page: 2, size: 20, total: 21 })
          : json(200, { items: Array.from({ length: 20 }, (_, index) => group('post', String(index + 1))), page: 1, size: 20, total: 21 }),
    });
    renderApp('/operator/reports');

    const section = within((await screen.findByRole('heading', { name: '게시판의 신고 (21개)' })).closest('section') as HTMLElement);
    await userEvent.click(section.getByRole('button', { name: '더 보기' }));
    expect(await section.findByText('글 99')).toBeInTheDocument();
    expect(section.queryByRole('button', { name: '더 보기' })).toBeNull();
    expect(calls(seen, 'GET', '/reports').map((request) => request.url.split('?')[1])).toEqual(['page=1&size=20', 'page=2&size=20']);
  });

  it('순수한 함수', () => {
    expect(boardReasonSummary({ spam: 0, abuse: 1, sexual: 2, illegal: 0, other: 0 })).toBe('욕설·괴롭힘 1 · 음란물 2');
    expect(boardReasonLabel('illegal')).toBe('불법 정보');
    expect(boardReasonLabel('new_reason')).toBe('new_reason');
    expect(boardOutcomeLabel({ outcome: null })).toBe('열림');
    expect(boardOutcomeLabel({ outcome: 'actioned' })).toBe('조치함');
    expect(targetLabel({ type: 'comment', id: '5', post_id: '3', deleted: false })).toBe('글 3 의 댓글 5');
    expect(targetPostPath({ type: 'post', id: '3', post_id: '3', deleted: true })).toBeNull();
    expect(targetPostPath({ type: 'comment', id: '5', post_id: '3', deleted: true })).toBe('/board/posts/3');
    expect(nextPage(21, 1, 20)).toBe(2);
    expect(nextPage(20, 1, 20)).toBeUndefined();
    expect(nextPage(0, 1, 20)).toBeUndefined();
  });
});
