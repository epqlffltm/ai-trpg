// web/apps/web/src/pages/operator/inquiries/InquiryBox.test.tsx
// 운영자의 문의함(메일함 모양). 상자의 탭과 수, 안 읽은 줄, 열면 읽음과 처음 연 사람, 답 쓰기(답한 사람, 답 메일),
// 하나 지우기, 고른 것 지우기, 상자 비우기(한 번 더 묻는다), 지운 기록(누가, 어떻게, 몇 개), 프로필 메뉴의 길. 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { AdminInquiry, InquiryAction } from '../../../api/inquiryAdmin';
import { REFRESH_PATH } from '../../../api/refresh';
import { openAccountMenu } from '../../../test/accountMenu';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../../test/fakeFetch';
import { renderApp } from '../../../test/renderApp';
import { actionLine, allSelected, boxOf, keepVisible, senderLabel, toggled } from './inquiryBoxView';

const ADMIN = '/api/v1/auth/admin/inquiries';
const OPERATOR = { public_id: '00000000-0000-4000-8000-0000000000f9', nickname: '운영자' };
const IDS = ['00000000-0000-4000-8000-0000000000a1', '00000000-0000-4000-8000-0000000000a2', '00000000-0000-4000-8000-0000000000a3'];

function base64Url(text: string): string {
  return btoa(String.fromCharCode(...new TextEncoder().encode(text)))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '');
}

function operatorToken(): string {
  return `${base64Url('{"alg":"RS256"}')}.${base64Url(JSON.stringify({ sub: 'u1', roles: ['operator'] }))}.sig`;
}

function inquiry(id: string, fields: Partial<AdminInquiry>): AdminInquiry {
  return {
    id,
    category: 'bug',
    title: '제목',
    body: '내용',
    status: 'open',
    created_at: '2026-11-09T01:00:00Z',
    reply: '',
    answered_at: null,
    sender: null,
    email: 'guest@example.com',
    read_at: null,
    read_by: null,
    answered_by: null,
    reply_sent_at: null,
    reply_discarded_at: null,
    ...fields,
  };
}

function box() {
  let rows: AdminInquiry[] = [
    inquiry(IDS[0] as string, { title: '로그인이 안 돼요', category: 'account', sender: { public_id: 'p1', nickname: '모험가' }, email: 'one@example.com' }),
    inquiry(IDS[1] as string, { title: '화면이 멈춰요' }),
    inquiry(IDS[2] as string, {
      title: '결제가 두 번',
      category: 'payment',
      status: 'answered',
      reply: '취소했습니다.',
      answered_at: '2026-11-08T05:00:00Z',
      answered_by: OPERATOR,
      read_at: '2026-11-08T04:00:00Z',
      read_by: OPERATOR,
      reply_sent_at: '2026-11-08T05:00:01Z',
    }),
  ];
  const actions: InquiryAction[] = [];
  const counts = () => ({
    all: rows.length,
    open: rows.filter((row) => row.status === 'open').length,
    answered: rows.filter((row) => row.status === 'answered').length,
    unread: rows.filter((row) => row.read_at === null).length,
  });
  const record = (kind: InquiryAction['kind'], ids: string[], folder = '') => {
    actions.unshift({
      id: actions.length + 1,
      kind,
      operator: OPERATOR,
      folder,
      inquiry_ids: ids,
      deleted_count: ids.length,
      created_at: '2026-11-09T02:00:00Z',
    });
  };
  const routes: Record<string, (request: SeenRequest) => Response> = {
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens(operatorToken())),
    'GET /api/v1/auth/me': () => json(200, { nickname: '운영자', public_id: 'u1' }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${ADMIN}`]: (request) => {
      const status = new URL(request.url, 'http://x').searchParams.get('status');
      return json(200, { items: rows.filter((row) => !status || row.status === status), counts: counts(), next_before: null });
    },
    [`GET ${ADMIN}/actions`]: () => json(200, { items: actions, next_before: null }),
    [`POST ${ADMIN}/delete`]: (request) => {
      const body = request.body as { ids?: string[]; folder?: string };
      const gone = rows.filter((row) => (body.ids ? body.ids.includes(row.id) : body.folder === 'all' || row.status === body.folder)).map((row) => row.id);
      rows = rows.filter((row) => !gone.includes(row.id));
      record(body.ids ? 'delete_selected' : 'empty_folder', gone, body.folder ?? '');
      return json(200, { deleted: gone.length });
    },
  };
  for (const id of IDS) {
    routes[`GET ${ADMIN}/${id}`] = () => {
      rows = rows.map((row) => (row.id === id && row.read_at === null ? { ...row, read_at: '2026-11-09T03:00:00Z', read_by: OPERATOR } : row));
      const row = rows.find((item) => item.id === id);
      return row ? json(200, row) : json(404, { detail: '그런 문의가 없습니다.', code: 'inquiry.not_found' });
    };
    routes[`DELETE ${ADMIN}/${id}`] = () => {
      rows = rows.filter((row) => row.id !== id);
      record('delete_one', [id]);
      return new Response(null, { status: 204 });
    };
    routes[`POST ${ADMIN}/${id}/reply`] = (request) => {
      const reply = (request.body as { reply: string }).reply;
      rows = rows.map((row) =>
        row.id === id ? { ...row, status: 'answered', reply, answered_at: '2026-11-09T04:00:00Z', answered_by: OPERATOR, reply_sent_at: null } : row,
      );
      return json(
        200,
        rows.find((row) => row.id === id),
      );
    };
  }
  return installFakeFetch(routes);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('운영자의 문의함', () => {
  it('상자의 탭에 수가 있고, 안 읽은 줄은 안 읽음이라 읽힌다. 열면 처음 연 사람이 적히고 안 읽은 수가 준다', async () => {
    box();
    renderApp('/operator/inquiries');

    const tabs = within(await screen.findByRole('navigation', { name: '상자' }));
    expect(await tabs.findByRole('button', { name: '답 기다림 2' })).toHaveAttribute('aria-current', 'page');
    expect(tabs.getByRole('button', { name: '모두 3' })).toBeInTheDocument();
    expect(screen.getByText('안 읽은 문의 2개')).toBeInTheDocument();
    const list = within(screen.getByRole('list', { name: '문의' }));
    expect(list.getAllByRole('listitem')).toHaveLength(2);

    await userEvent.click(list.getByRole('button', { name: /안 읽음\s*로그인이 안 돼요/ }));
    const detail = within(await screen.findByRole('article', { name: '로그인이 안 돼요' }));
    expect(detail.getByText('모험가 (one@example.com)')).toBeInTheDocument();
    expect(await detail.findByText(/^운영자 · /)).toBeInTheDocument();
    expect(await screen.findByText('안 읽은 문의 1개')).toBeInTheDocument();
  });

  it('답을 쓰면 누가 답했는지와 답 메일이 보이고 답함 상자로 간다', async () => {
    const { seen } = box();
    renderApp(`/operator/inquiries?box=open&id=${IDS[1]}`);

    const form = within(await screen.findByRole('form', { name: '답 쓰기' }));
    await userEvent.type(form.getByRole('textbox', { name: '답' }), ' 고쳤습니다. ');
    await userEvent.click(form.getByRole('button', { name: '답 보내기' }));

    const answered = within(await screen.findByRole('region', { name: '보낸 답' }));
    expect(answered.getByText(/운영자이\(가\) .*에 답했습니다. 답 메일을 보내는 중입니다./)).toBeInTheDocument();
    expect(seen.find((request) => request.url === `${ADMIN}/${IDS[1]}/reply`)?.body).toEqual({ reply: '고쳤습니다.' });
    expect(await within(screen.getByRole('navigation', { name: '상자' })).findByRole('button', { name: '답함 2' })).toBeInTheDocument();
  });

  it('고른 것을 지우고 상자를 비운다. 둘 다 한 번 더 묻고, 지운 기록에 누가 어떻게 지웠는지 남는다', async () => {
    box();
    renderApp('/operator/inquiries?box=all');

    const list = within(await screen.findByRole('list', { name: '문의' }));
    expect(await list.findAllByRole('listitem')).toHaveLength(3);
    await userEvent.click(list.getByRole('checkbox', { name: '로그인이 안 돼요 고르기' }));
    await userEvent.click(list.getByRole('checkbox', { name: '화면이 멈춰요 고르기' }));
    await userEvent.click(screen.getByRole('button', { name: '고른 것 지우기 (2)' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '지우기' }));
    expect(await screen.findByText('문의 2개를 지웠습니다.')).toBeInTheDocument();
    expect(await list.findAllByRole('listitem')).toHaveLength(1);

    await userEvent.click(screen.getByRole('button', { name: '이 상자 비우기' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '모두 지우기' }));
    expect(await screen.findByText('이 상자에 문의가 없습니다.')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: '지운 기록' }));
    const actions = within(await screen.findByRole('list', { name: '지운 일' }));
    expect(actions.getAllByRole('listitem').map((item) => item.firstChild?.textContent)).toEqual([
      '운영자 · 상자 비움(모두) · 1개',
      '운영자 · 고른 것 지움 · 2개',
    ]);
  });

  it('보이는 문의를 모두 고르고, 열린 문의는 하나씩 지운다', async () => {
    box();
    renderApp(`/operator/inquiries?box=open&id=${IDS[0]}`);

    await userEvent.click(await screen.findByRole('checkbox', { name: '보이는 문의 모두 고르기' }));
    expect(screen.getByRole('button', { name: '고른 것 지우기 (2)' })).toBeInTheDocument();

    const detail = within(await screen.findByRole('article', { name: '로그인이 안 돼요' }));
    await userEvent.click(detail.getByRole('button', { name: '이 문의 지우기' }));
    await userEvent.click(within(await screen.findByRole('dialog')).getByRole('button', { name: '지우기' }));
    expect(await within(screen.getByRole('list', { name: '문의' })).findAllByRole('listitem')).toHaveLength(1);
    expect(screen.queryByRole('article')).toBeNull();
    expect(screen.getByRole('button', { name: '고른 것 지우기 (1)' })).toBeInTheDocument();
  });

  it('프로필 메뉴의 운영 묶음에서 문의함으로 간다', async () => {
    box();
    renderApp('/operator/inquiries');

    const menu = await openAccountMenu();
    expect(within(menu.getByRole('list', { name: '운영' })).getByRole('link', { name: '문의함' })).toHaveAttribute('href', '/operator/inquiries');
  });
});

describe('문의함의 순수한 함수', () => {
  it('상자, 보낸 사람, 고르기, 지운 일의 한 줄', () => {
    expect(boxOf('answered')).toBe('answered');
    expect(boxOf('trash')).toBe('open');
    expect(senderLabel({ sender: null, email: 'a@b.c' })).toBe('a@b.c');
    expect([...toggled(new Set(['a']), 'b')]).toEqual(['a', 'b']);
    expect([...toggled(new Set(['a']), 'a')]).toEqual([]);
    expect(allSelected(new Set(['a', 'b']), ['a', 'b'])).toBe(true);
    expect(allSelected(new Set(), [])).toBe(false);
    expect([...keepVisible(new Set(['a', 'gone']), ['a', 'b'])]).toEqual(['a']);
    expect(actionLine({ id: 1, kind: 'retention', operator: null, folder: '', inquiry_ids: [], deleted_count: 4, created_at: '' })).toBe(
      '정리 명령 · 보관 기간이 지나 지움 · 4개',
    );
  });
});
