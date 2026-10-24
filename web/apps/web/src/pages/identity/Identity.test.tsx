// web/apps/web/src/pages/identity/Identity.test.tsx
// 본인인증(A3). 내 정보에서 가기, 시험용 본인확인 창(빠른 고르기, 생일, 사람 식별값)으로 인증하고 토큰을 갱신하기,
// 만 14세 미만이면 로그인 화면으로 보내기, 다른 계정이 쓴 사람 알리기, 홈의 본인인증 안내. 순수한 함수.

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/errors';
import { REFRESH_PATH } from '../../api/refresh';
import { getSession } from '../../api/session';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';
import { describeIdentityProblem } from './identityProblem';
import { birthDateForAge, defaultFakeDi, diHint, fakeIdentityToken, koreanToday, providerKind } from './identityProvider';

const VERIFY = '/api/v1/auth/identity/verify';
const UNVERIFIED = { verified: false, legal_adult: false, adult_content: false };
const ADULT = { verified: true, legal_adult: true, adult_content: true };

function me(identity = UNVERIFIED) {
  return { nickname: '모험가', public_id: ME, username: 'p', email: 'e@x', identity, guardian_consent: 'none', consents_pending: [], withdrawal_scheduled_at: null };
}

function signedIn(answer: () => Response) {
  let identity = UNVERIFIED;
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, me(identity)),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`POST ${VERIFY}`]: () => {
      const response = answer();
      if (response.status === 201) identity = ADULT;
      return response;
    },
  });
}

function count(seen: SeenRequest[], method: string, url: string): number {
  return seen.filter((request) => request.method === method && request.url === url).length;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('본인인증', () => {
  it('내 정보에서 가서, 시험용 창으로 성인을 골라 인증하면 상태를 바꾸고 토큰을 한 번 갱신한다', async () => {
    const { seen } = signedIn(() => json(201, { identity: ADULT }));
    renderApp('/me');

    await userEvent.click(await screen.findByRole('link', { name: '본인인증하기' }));
    expect(await screen.findByRole('heading', { name: '휴대폰 본인인증' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: '성인(만 30세)' }));
    expect(screen.getByLabelText('사람 식별값')).toHaveValue(defaultFakeDi(ME));
    const refreshes = count(seen, 'POST', REFRESH_PATH);
    await userEvent.click(screen.getByRole('button', { name: '이 사람으로 인증하기' }));

    expect(await screen.findByRole('heading', { name: '본인인증을 마쳤습니다' })).toBeInTheDocument();
    expect(screen.getByText('상태: 했음(성인, 성인용 내용 열림)')).toBeInTheDocument();
    const sent = seen.filter((request) => request.method === 'POST' && request.url === VERIFY);
    expect(sent[0]?.body).toEqual({ token: fakeIdentityToken(defaultFakeDi(ME), birthDateForAge(koreanToday(), 30)) });
    await vi.waitFor(() => expect(count(seen, 'POST', REFRESH_PATH)).toBeGreaterThan(refreshes));
  });

  it('만 14세 미만이면 계정이 막혔다고 알리며 로그인 화면으로 보낸다', async () => {
    signedIn(() => json(403, { detail: 'x', code: 'identity_under_age' }));
    renderApp('/me/identity');

    await userEvent.click(await screen.findByRole('button', { name: '만 13세(막힘)' }));
    await userEvent.click(screen.getByRole('button', { name: '이 사람으로 인증하기' }));
    expect(await screen.findByText(/만 14세 미만은 이용할 수 없어 계정을 막았습니다/)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '로그인' })).toBeInTheDocument();
    expect(getSession()).toBeNull();
  });

  it('다른 계정이 쓴 사람이면 까닭을 알리고, 식별값이 틀리면 막는다', async () => {
    signedIn(() => json(409, { detail: 'x', code: 'identity_in_use' }));
    renderApp('/me/identity');

    const di = await screen.findByLabelText('사람 식별값');
    await userEvent.clear(di);
    await userEvent.type(di, '한글');
    expect(screen.getByText('영문, 숫자, + / = _ - 만 씁니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '이 사람으로 인증하기' })).toBeDisabled();
    await userEvent.clear(di);
    await userEvent.type(di, 'someone');
    await userEvent.click(screen.getByRole('button', { name: '이 사람으로 인증하기' }));
    expect(await screen.findByText(/다른 계정이 이미 이 사람으로 본인인증을 했습니다/)).toBeInTheDocument();
  });

  it('홈에서 본인인증 전이면 한 줄과 본인인증으로 가는 길을 보인다', async () => {
    signedIn(() => json(201, { identity: ADULT }));
    renderApp('/');
    await userEvent.click(await screen.findByRole('link', { name: '본인인증하기' }));
    expect(await screen.findByRole('heading', { name: '본인인증' })).toBeInTheDocument();
  });
});

describe('본인인증의 순수한 함수', () => {
  it('업체의 갈래, 식별값, 생일, 한국 날짜', () => {
    expect(providerKind(undefined)).toBe('fake');
    expect(providerKind('none')).toBe('none');
    expect(defaultFakeDi('00000000-0000-4000-8000-0000000000e1')).toBe('dev-00000000-0000-4000-8000-0000000000e1');
    expect(diHint('')).toContain('적어');
    expect(diHint('a'.repeat(129))).toContain('128');
    expect(diHint('ok_1')).toBeNull();
    expect(birthDateForAge('2026-10-24', 17)).toBe('2009-10-24');
    expect(birthDateForAge('2028-02-29', 1)).toBe('2027-02-28');
    expect(koreanToday(new Date('2026-10-24T16:00:00Z'))).toBe('2026-10-25');
  });

  it('실패: 만 14세 미만은 로그아웃, 이미 인증은 다시 읽기, 503 은 잠시 뒤', () => {
    expect(describeIdentityProblem(new ApiError({ status: 403, detail: 'x', code: 'identity_under_age' })).signedOut).toBe(true);
    expect(describeIdentityProblem(new ApiError({ status: 409, detail: 'x', code: 'identity_already_verified' })).verified).toBe(true);
    expect(describeIdentityProblem(new ApiError({ status: 503, detail: 'x' })).message).toContain('지금은 본인인증을 할 수 없습니다');
    expect(describeIdentityProblem(new ApiError({ status: 400, detail: 'x', code: 'identity_token_invalid' })).message).toContain('처음부터');
  });
});
