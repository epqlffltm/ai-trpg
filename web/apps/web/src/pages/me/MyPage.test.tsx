// web/apps/web/src/pages/me/MyPage.test.tsx
// 마이페이지(A5, Stitch 10번). 로그인해야 열리는지, 프로필 머리와 탭 넷, 비밀번호 바꾸기, 모든 기기 로그아웃, 선택 동의를 켜고 끄는 것, 탈퇴 요청, 친구 초대(#990), 활동 배지(#193)를 본다.

import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { REFRESH_PATH } from '../../api/refresh';
import { getSession } from '../../api/session';
import { formatDate, formatDateTime } from '../../format/dateTime';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { earnedLine } from './badgeView';
import { requestedNotice } from './WithdrawalSection';

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

const BADGES = {
  earned: 1,
  badges: [
    { id: 'first_attendance', name: '첫 출석', description: '처음으로 출석 보상을 받았다', earned_at: '2026-11-08T03:00:00Z' },
    { id: 'identity_verified', name: '본인인증', description: '휴대폰 본인인증을 마쳤다', earned_at: null },
  ],
};

const CONSENTS = [consent('terms', true, 1), consent('privacy', true, 1), consent('marketing', false, null)];

function signedIn(extra: Record<string, (request: SeenRequest) => Response> = {}) {
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, ME),
    'GET /api/v1/auth/me/consents': () => json(200, { items: CONSENTS }),
    'GET /api/v1/auth/me/invite': () => json(200, { code: 'ABCD2345', rewarded: 1, limit: 5 }),
    'GET /api/v1/auth/me/badges': () => json(200, BADGES),
    ...extra,
  });
}

describe('MyPage', () => {
  it('로그인하지 않았으면 로그인으로 보낸다', async () => {
    installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }) });
    renderApp('/me');

    expect(await screen.findByRole('heading', { name: '로그인' })).toBeInTheDocument();
  });

  it('맨 위에 닉네임과 아이디, 탭 넷이 있고 처음은 내 계정이다. 탭을 고르면 그 칸만 보인다', async () => {
    signedIn({
      'GET /api/v1/billing/wallet': () => json(200, { paid: '80', free: '10', total: '90', next_expiry: null }),
    });
    renderApp('/me');

    expect(await screen.findByRole('heading', { level: 1, name: '모험가' })).toBeInTheDocument();
    expect(screen.getByText('@player_one')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '회원정보 수정' })).toHaveAttribute('href', '/me');
    expect(screen.getByRole('link', { name: '제작자 페이지' })).toHaveAttribute('href', '/me?tab=creator');
    const tabs = within(screen.getByRole('navigation', { name: '마이페이지' }));
    expect(tabs.getAllByRole('link').map((link) => link.textContent)).toEqual(['내 계정', '내 포인트', '설정', '제작자']);
    expect(tabs.getByRole('link', { name: '내 계정' })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('heading', { name: '비밀번호 바꾸기' })).toBeInTheDocument();

    await userEvent.click(tabs.getByRole('link', { name: '내 포인트' }));
    const gold = within(await screen.findByRole('region', { name: '골드' }));
    expect(await gold.findByText('80')).toBeInTheDocument();
    expect(gold.getByRole('link', { name: '충전' })).toHaveAttribute('href', '/wallet/charge');
    expect(screen.getByRole('link', { name: '내 포인트' })).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('heading', { name: '비밀번호 바꾸기' })).toBeNull();
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

  it('탈퇴는 남은 크레딧을 알리고, 비밀번호를 받아 요청한 뒤 지울 시각을 적어 로그인으로 보낸다', async () => {
    const scheduledAt = '2026-11-09T03:00:00Z';
    const { seen } = signedIn({
      'GET /api/v1/billing/wallet': () => json(200, { paid: '80', free: '10', total: '90', next_expiry: null }),
      'POST /api/v1/auth/me/withdrawal': () => json(202, { withdrawal_scheduled_at: scheduledAt }),
    });
    renderApp('/me');

    expect(await screen.findByText(/지금 남은 것: 골드 80 · 실버 10/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '탈퇴하기' }));
    const dialog = screen.getByRole('dialog', { name: '탈퇴하기' });
    const send = within(dialog).getByRole('button', { name: '탈퇴 요청하기' });
    expect(send).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText('비밀번호'), 'my-pass-1234');
    await userEvent.click(send);

    expect(await screen.findByText(new RegExp(`${formatDateTime(scheduledAt)}에 계정을 지웁니다`))).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '로그인' })).toBeInTheDocument();
    expect(getSession()).toBeNull();
    expect(seen.find((request) => request.url === '/api/v1/auth/me/withdrawal')?.body).toEqual({
      password: 'my-pass-1234',
    });
  });

  it('탈퇴의 비밀번호가 틀리면 그 칸에 서버의 글을 보이고 그대로 머문다', async () => {
    signedIn({
      'GET /api/v1/billing/wallet': () => json(503, { detail: 'down' }),
      'POST /api/v1/auth/me/withdrawal': () => json(400, { password: ['비밀번호가 올바르지 않습니다.'] }),
    });
    renderApp('/me');

    await userEvent.click(await screen.findByRole('button', { name: '탈퇴하기' }));
    const dialog = screen.getByRole('dialog', { name: '탈퇴하기' });
    await userEvent.type(within(dialog).getByLabelText('비밀번호'), 'wrong');
    await userEvent.click(within(dialog).getByRole('button', { name: '탈퇴 요청하기' }));

    expect(await within(dialog).findByText('비밀번호가 올바르지 않습니다.')).toBeInTheDocument();
    expect(getSession()?.accessToken).toBe('a1');
    // 잔액을 읽지 못해도 사라진다는 문장은 보인다
    expect(screen.getByText(/남은 크레딧은 모두 사라지고/)).toBeInTheDocument();
  });

  it('탈퇴를 너무 많이 틀리면 기다리게 한다', async () => {
    signedIn({
      'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
      'POST /api/v1/auth/me/withdrawal': () =>
        new Response(JSON.stringify({ detail: 'too many' }), {
          status: 429,
          headers: { 'Content-Type': 'application/json', 'Retry-After': '30' },
        }),
    });
    renderApp('/me');

    await userEvent.click(await screen.findByRole('button', { name: '탈퇴하기' }));
    const dialog = screen.getByRole('dialog', { name: '탈퇴하기' });
    await userEvent.type(within(dialog).getByLabelText('비밀번호'), 'my-pass-1234');
    await userEvent.click(within(dialog).getByRole('button', { name: '탈퇴 요청하기' }));

    expect(await within(dialog).findByText(/30초 뒤에 다시 시도하세요/)).toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: /초 뒤에 다시/ })).toBeDisabled();
  });
});

describe('requestedNotice', () => {
  it('지울 시각을 모르면 7일 뒤라고 쓴다', () => {
    expect(requestedNotice(null)).toContain('7일 뒤에 계정을 지웁니다');
  });

  it('친구 초대에 내 코드와 받은 보상의 수를 보이고 가입 주소를 복사한다', async () => {
    signedIn();
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    renderApp('/me?tab=settings');

    const invite = (await screen.findByRole('heading', { name: '친구 초대' })).closest('section') as HTMLElement;
    expect(await within(invite).findByText('ABCD2345')).toBeInTheDocument();
    expect(within(invite).getByText('받은 초대 보상 1 / 5번')).toBeInTheDocument();
    await userEvent.click(within(invite).getByRole('button', { name: '가입 주소 복사' }));

    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/signup?invite=ABCD2345`);
    expect(await within(invite).findByRole('button', { name: '복사했습니다' })).toBeInTheDocument();
  });
});

describe('칸까지 내리기', () => {
  it('주소의 #가 가리키는 칸(프로필 메뉴의 차단 관리)까지 내린다', async () => {
    const original = Element.prototype.scrollIntoView;
    const scrolled = vi.fn();
    Element.prototype.scrollIntoView = scrolled;
    signedIn();
    renderApp('/me?tab=settings#my-blocks-heading');

    const heading = await screen.findByRole('heading', { name: '차단' });
    await vi.waitFor(() => expect(scrolled).toHaveBeenCalled());
    expect(scrolled.mock.contexts[0]).toBe(heading);
    Element.prototype.scrollIntoView = original;
  });
});

describe('활동 배지', () => {
  it('설정 탭에 모든 배지를 보이고, 받은 것은 받은 날, 아직인 것은 흐리게 보인다', async () => {
    signedIn();
    renderApp('/me?tab=settings');

    const section = (await screen.findByRole('heading', { name: '활동 배지' })).closest('section') as HTMLElement;
    expect(await within(section).findByText('받은 배지 1 / 2개')).toBeInTheDocument();
    const items = within(within(section).getByRole('list', { name: '활동 배지' })).getAllByRole('listitem');
    const [earned, locked] = items as [HTMLElement, HTMLElement];
    expect(items).toHaveLength(2);
    expect(within(earned).getByText('첫 출석')).toBeInTheDocument();
    expect(within(earned).getByText(`${formatDate('2026-11-08T03:00:00Z')}에 받음`)).toBeInTheDocument();
    expect(earned).not.toHaveClass('badge-item--locked');
    expect(within(locked).getByText('아직 받지 않음')).toBeInTheDocument();
    expect(locked).toHaveClass('badge-item--locked');
  });

  it('읽지 못하면 다시 시도한다', async () => {
    let calls = 0;
    signedIn({
      'GET /api/v1/auth/me/badges': () => {
        calls += 1;
        return calls === 1 ? json(500, { detail: 'boom' }) : json(200, BADGES);
      },
    });
    renderApp('/me?tab=settings');

    const section = (await screen.findByRole('heading', { name: '활동 배지' })).closest('section') as HTMLElement;
    await userEvent.click(await within(section).findByRole('button', { name: '다시 시도' }));
    expect(await within(section).findByText('받은 배지 1 / 2개')).toBeInTheDocument();
  });

  it('받은 수의 줄', () => {
    expect(earnedLine(0, 6)).toBe('받은 배지 0 / 6개');
  });
});
