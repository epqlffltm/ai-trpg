// web/apps/web/src/pages/support/Support.test.tsx
// 고객센터(/support). 로그인하지 않아도 답 받을 주소를 적어 문의를 보내고, 로그인했으면 주소 없이 보내고 내 문의와 답을 본다.
// 칸의 오류와 너무 잦은 보내기(429), 왼쪽 메뉴 열과 마이페이지에서 오는 길. 순수한 함수.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { canSend, toDraft } from './inquiryView';

const INQUIRIES = '/api/v1/auth/inquiries';
const MINE = '/api/v1/auth/me/inquiries';
const ME = {
  public_id: '0b6f1d2e-0000-4000-8000-000000000001',
  username: 'player_one',
  email: 'one@example.com',
  nickname: '모험가',
  identity: { verified: true, legal_adult: true, adult_content: false },
  guardian_consent: 'none',
  consents_pending: [],
  withdrawal_scheduled_at: null,
};
const ANSWERED = {
  id: '00000000-0000-4000-8000-0000000000a1',
  category: 'payment',
  title: '결제가 두 번 됐어요',
  body: '어제 두 번 나갔습니다.',
  status: 'answered',
  created_at: '2026-11-08T03:00:00Z',
  reply: '한 번을 취소했습니다.',
  answered_at: '2026-11-08T05:00:00Z',
};

function signedOut(send: (request: SeenRequest) => Response = () => json(201, { id: 'x', created_at: '2026-11-09T00:00:00Z' })) {
  return installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }), [`POST ${INQUIRIES}`]: send });
}

function signedIn() {
  let items: unknown[] = [];
  const fake = installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, ME),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`GET ${MINE}`]: () => json(200, { items, next_before: null }),
    [`POST ${INQUIRIES}`]: () => {
      items = [ANSWERED];
      return json(201, { id: ANSWERED.id, created_at: ANSWERED.created_at });
    },
  });
  return fake;
}

function sent(seen: SeenRequest[]): Record<string, unknown>[] {
  return seen.filter((request) => request.method === 'POST' && request.url === INQUIRIES).map((request) => request.body as Record<string, unknown>);
}

async function fill(email?: string) {
  const form = within(await screen.findByRole('form', { name: '문의 보내기' }));
  await userEvent.selectOptions(form.getByRole('combobox', { name: '종류' }), 'account');
  await userEvent.type(form.getByRole('textbox', { name: '제목' }), '로그인이 안 돼요');
  await userEvent.type(form.getByRole('textbox', { name: '내용' }), '코드 메일이 오지 않습니다.');
  if (email !== undefined) await userEvent.type(form.getByRole('textbox', { name: '답 받을 이메일' }), email);
  return form;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('고객센터', () => {
  it('로그인하지 않아도 답 받을 주소를 적어 보낸다. 주소가 없으면 보내지 못하고, 보내면 칸을 비운다', async () => {
    const { seen } = signedOut();
    renderApp('/support');

    const form = await fill();
    expect(form.getByRole('button', { name: '문의 보내기' })).toBeDisabled();
    await userEvent.type(form.getByRole('textbox', { name: '답 받을 이메일' }), 'guest@example.com');
    await userEvent.click(form.getByRole('button', { name: '문의 보내기' }));

    expect(await form.findByText(/문의를 받았습니다. 답은 적은 주소로 메일을 보냅니다/)).toBeInTheDocument();
    expect(sent(seen)).toEqual([{ category: 'account', title: '로그인이 안 돼요', body: '코드 메일이 오지 않습니다.', email: 'guest@example.com' }]);
    expect(form.getByRole('textbox', { name: '제목' })).toHaveValue('');
    expect(screen.queryByRole('heading', { name: '내 문의' })).toBeNull();
  });

  it('로그인했으면 주소 없이 보내고, 내 문의를 다시 읽어 답을 펼쳐 본다', async () => {
    const { seen } = signedIn();
    renderApp('/support');

    expect(await screen.findByText('아직 보낸 문의가 없습니다.')).toBeInTheDocument();
    const form = await fill();
    expect(form.queryByRole('textbox', { name: '답 받을 이메일' })).toBeNull();
    await userEvent.click(form.getByRole('button', { name: '문의 보내기' }));

    expect(sent(seen)[0]).not.toHaveProperty('email');
    const list = within(await screen.findByRole('list', { name: '내 문의' }));
    expect(list.getByText('결제·환불')).toBeInTheDocument();
    expect(list.getByText('답함')).toBeInTheDocument();
    await userEvent.click(list.getByText('결제가 두 번 됐어요'));
    expect(within(list.getByLabelText('답')).getByText('한 번을 취소했습니다.')).toBeVisible();
  });

  it('칸의 오류는 그 칸에, 너무 자주 보내면 기다릴 시간만큼 막는다', async () => {
    let calls = 0;
    signedOut(() => {
      calls += 1;
      return calls === 1
        ? json(400, { detail: '입력이 올바르지 않습니다.', errors: { email: ['올바른 이메일 주소를 입력하세요.'] } })
        : json(429, { detail: 'x', retry_after: 30 }, { 'Retry-After': '30' });
    });
    renderApp('/support');

    const form = await fill('guest@example.com');
    await userEvent.click(form.getByRole('button', { name: '문의 보내기' }));
    expect(await form.findByText('올바른 이메일 주소를 입력하세요.')).toBeInTheDocument();

    await userEvent.click(form.getByRole('button', { name: '문의 보내기' }));
    expect(await form.findByRole('button', { name: /초 뒤에 다시/ })).toBeDisabled();
  });

  it('왼쪽 메뉴 열의 맨 아래와 마이페이지에서 고객센터로 간다', async () => {
    signedIn();
    renderApp('/me?tab=settings');

    const sidebar = within(await screen.findByRole('complementary', { name: '사이트 메뉴' }));
    expect(within(sidebar.getByRole('navigation', { name: '안내' })).getByRole('link', { name: '고객센터' })).toHaveAttribute('href', '/support');
    const section = (await screen.findByRole('heading', { name: '고객센터' })).closest('section') as HTMLElement;
    expect(within(section).getByRole('link', { name: '문의 보내기와 내 문의' })).toHaveAttribute('href', '/support');
  });
});

describe('문의의 입력', () => {
  const form = { category: 'bug' as const, title: ' 멈춰요 ', body: ' 방에서 ', email: ' a@b.c ' };

  it('로그인하지 않았으면 주소가 있어야 보내고, 보낼 때 앞뒤 공백을 떼며, 로그인했으면 주소를 싣지 않는다', () => {
    expect(canSend({ ...form, email: '' }, false)).toBe(false);
    expect(canSend({ ...form, email: '' }, true)).toBe(true);
    expect(canSend({ ...form, category: '' }, true)).toBe(false);
    expect(toDraft(form, false)).toEqual({ category: 'bug', title: '멈춰요', body: '방에서', email: 'a@b.c' });
    expect(toDraft(form, true)).toEqual({ category: 'bug', title: '멈춰요', body: '방에서' });
  });
});
