// web/apps/web/src/pages/me/MyPage.test.tsx
// 마이페이지(A5). 로그인해야 열리는지, 비밀번호 바꾸기, 모든 기기 로그아웃, 선택 동의를 켜고 끄는 것을 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { getSession } from '../../api/session';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';

const ME = {
  public_id: '0b6f1d2e-0000-4000-8000-000000000001',
  username: 'player_one',
  email: 'one@example.com',
  nickname: '모험가',
  identity: { verified: false, legal_adult: false, adult_content: false },
  guardian_consent: 'none',
  consents_pending: [],
  withdrawal_scheduled_at: null,
};

function consent(item: string, required: boolean, agreedVersion: number | null) {
  return {
    item,
    version: 1,
    required,
    pending: false,
    agreed_version: agreedVersion,
    agreed_at: agreedVersion ? '2026-10-20T03:00:00Z' : null,
  };
}

const CONSENTS = [consent('terms', true, 1), consent('privacy', true, 1), consent('marketing', false, null)];

function signedIn(extra: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, ME),
    'GET /api/v1/auth/me/consents': () => json(200, { items: CONSENTS }),
    ...extra,
  });
}

describe('MyPage', () => {
  it('로그인하지 않았으면 로그인으로 보낸다', async () => {
    installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }) });
    renderApp('/me');

    expect(await screen.findByRole('heading', { name: '로그인' })).toBeInTheDocument();
  });

  it('계정을 보이고, 미성년자가 아니면 보호자 동의 줄을 숨긴다', async () => {
    signedIn();
    renderApp('/me');

    expect(await screen.findByText('one@example.com')).toBeInTheDocument();
    expect(screen.getByText('player_one')).toBeInTheDocument();
    expect(screen.getByText('하지 않음')).toBeInTheDocument();
    expect(screen.queryByText('보호자 동의')).not.toBeInTheDocument();
    expect(await screen.findAllByText(/1판에 동의\(2026년 10월 20일\)/)).toHaveLength(2);
  });

  it('비밀번호를 바꾸면 새 토큰으로 이어지고 알린다', async () => {
    const { seen } = signedIn({ 'POST /api/v1/auth/password/change': () => json(200, tokens('a2')) });
    renderApp('/me');

    await userEvent.type(await screen.findByLabelText('현재 비밀번호'), 'old-pass-1234');
    await userEvent.type(screen.getByLabelText('새 비밀번호'), 'new-pass-5678');
    await userEvent.type(screen.getByLabelText('새 비밀번호 확인'), 'new-pass-5678');
    await userEvent.click(screen.getByRole('button', { name: '바꾸기' }));

    expect(await screen.findByText(/다른 기기에서는 로그아웃됐습니다/)).toBeInTheDocument();
    expect(getSession()?.accessToken).toBe('a2');
    expect(screen.getByLabelText('현재 비밀번호')).toHaveValue('');
    expect(seen.find((request) => request.url === '/api/v1/auth/password/change')?.body).toEqual({
      current_password: 'old-pass-1234',
      new_password: 'new-pass-5678',
    });
  });

  it('현재 비밀번호가 틀리면 그 칸에 서버의 글을 보인다', async () => {
    signedIn({
      'POST /api/v1/auth/password/change': () =>
        json(400, { current_password: ['현재 비밀번호가 올바르지 않습니다.'] }),
    });
    renderApp('/me');

    await userEvent.type(await screen.findByLabelText('현재 비밀번호'), 'wrong');
    await userEvent.type(screen.getByLabelText('새 비밀번호'), 'new-pass-5678');
    await userEvent.type(screen.getByLabelText('새 비밀번호 확인'), 'new-pass-5678');
    await userEvent.click(screen.getByRole('button', { name: '바꾸기' }));

    expect(await screen.findByText('현재 비밀번호가 올바르지 않습니다.')).toBeInTheDocument();
    expect(getSession()?.accessToken).toBe('a1');
  });

  it('모든 기기에서 로그아웃하면 한 번 더 묻고, 마치면 로그인으로 보낸다', async () => {
    const { seen } = signedIn({ 'POST /api/v1/auth/logout-all': () => new Response(null, { status: 204 }) });
    renderApp('/me');

    await userEvent.click(await screen.findByRole('button', { name: '모든 기기에서 로그아웃' }));
    const dialog = screen.getByRole('dialog', { name: '모든 기기에서 로그아웃' });
    await userEvent.click(within(dialog).getByRole('button', { name: '로그아웃하기' }));

    expect(await screen.findByText(/모든 기기에서 로그아웃했습니다/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '로그인' })).toBeInTheDocument();
    expect(getSession()).toBeNull();
    expect(seen.some((request) => request.url === '/api/v1/auth/logout-all')).toBe(true);
  });

  it('선택 동의는 문서를 보고 켜고, 바로 끈다', async () => {
    const agreed = [CONSENTS[0], CONSENTS[1], consent('marketing', false, 1)];
    const { seen } = signedIn({
      'PUT /api/v1/auth/me/consents/marketing': () => json(200, { items: agreed }),
      'DELETE /api/v1/auth/me/consents/marketing': () => json(200, { items: CONSENTS }),
    });
    renderApp('/me');

    const marketing = await screen.findByLabelText('[선택] 마케팅 정보 수신');
    await userEvent.click(marketing);
    const dialog = await screen.findByRole('dialog', { name: '마케팅 정보 수신' });
    expect(marketing).not.toBeChecked();
    await userEvent.click(within(dialog).getByRole('button', { name: '동의하기' }));

    expect(await screen.findByLabelText('[선택] 마케팅 정보 수신')).toBeChecked();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(seen.find((request) => request.method === 'PUT')?.body).toEqual({ version: 1 });

    await userEvent.click(screen.getByLabelText('[선택] 마케팅 정보 수신'));
    expect(await screen.findByLabelText('[선택] 마케팅 정보 수신')).not.toBeChecked();
    expect(seen.some((request) => request.method === 'DELETE')).toBe(true);
  });

  it('필수 동의에는 끄는 칸이 없다', async () => {
    signedIn();
    renderApp('/me');

    expect(await screen.findByText('[필수] 이용약관')).toBeInTheDocument();
    expect(screen.queryByRole('checkbox', { name: /이용약관/ })).not.toBeInTheDocument();
  });
});
