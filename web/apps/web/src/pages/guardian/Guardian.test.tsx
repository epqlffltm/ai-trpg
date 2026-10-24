// web/apps/web/src/pages/guardian/Guardian.test.tsx
// 보호자 동의(A4). 미성년자: 내 정보에서 가기, 보호자 이메일로 부탁하기(내 이메일 막기, 다시 보내기), 실패(이미 동의함, 너무 자주, 칸의 글),
// 단계마다의 안내. 보호자: 로그인 없이 링크의 화면에서 본인인증으로 동의하기, 철회하기, 쓸 수 없는 링크. 순수한 함수.

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../api/errors';
import { REFRESH_PATH } from '../../api/refresh';
import type { Me } from '../../api/types';
import { isAuthPath } from '../../auth/safeReturnPath';
import { installFakeFetch, json, tokens, type SeenRequest } from '../../test/fakeFetch';
import { renderApp } from '../../test/renderApp';
import { ME } from '../../test/tableFixtures';
import { birthDateForAge, fakeIdentityToken, koreanToday } from '../identity/identityProvider';
import { describeConsentProblem, describeRequestProblem, LINK_INVALID } from './guardianProblem';
import { parseGuardianLink } from './guardianLink';
import { GUARDIAN_FAKE_DI } from './guardianPresets';
import { canRequest, guardianEmailHint, guardianStage } from './guardianView';

const GUARDIAN = '/api/v1/auth/guardian';
const MINOR = { verified: true, legal_adult: false, adult_content: false };
const ADULT = { verified: true, legal_adult: true, adult_content: true };

function me(identity: Me['identity'], consent: Me['guardian_consent']) {
  return { nickname: '모험가', public_id: ME, username: 'p', email: 'me@x.kr', identity, guardian_consent: consent, consents_pending: [], withdrawal_scheduled_at: null };
}

function minor(answer: () => Response, start: Me['guardian_consent'] = 'none', after: Me['guardian_consent'] = start, identity: Me['identity'] = MINOR) {
  let consent = start;
  return installFakeFetch({
    [`POST ${REFRESH_PATH}`]: () => json(200, tokens('a1')),
    'GET /api/v1/auth/me': () => json(200, me(identity, consent)),
    'GET /api/v1/auth/me/consents': () => json(200, { items: [] }),
    'GET /api/v1/billing/wallet': () => json(200, { paid: '0', free: '0', total: '0', next_expiry: null }),
    [`POST ${GUARDIAN}/request`]: () => {
      const response = answer();
      consent = response.status === 202 ? 'requested' : after;
      return response;
    },
  });
}

function guardian(routes: Record<string, () => Response>) {
  return installFakeFetch({ [`POST ${REFRESH_PATH}`]: () => json(401, { detail: 'no cookie' }), ...routes });
}

function sent(seen: SeenRequest[], url: string): unknown[] {
  return seen.filter((request) => request.method === 'POST' && request.url === url).map((request) => request.body);
}

function count(seen: SeenRequest[], url: string): number {
  return seen.filter((request) => request.method === 'GET' && request.url === url).length;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('보호자에게 부탁하기', () => {
  it('내 정보에서 가서, 내 이메일은 막고, 보호자 이메일로 보내면 기다리는 중이 되고 다시 보낼 수 있다', async () => {
    const { seen } = minor(() => json(202, { detail: '보냈다', guardian_consent: 'requested' }));
    renderApp('/me');

    await userEvent.click(await screen.findByRole('link', { name: '부탁하기' }));
    const email = await screen.findByLabelText('보호자의 이메일');
    await userEvent.type(email, 'ME@x.kr');
    expect(screen.getByText('보호자의 이메일을 적어 주세요. 내 이메일은 쓸 수 없습니다.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '동의 요청 보내기' })).toBeDisabled();
    await userEvent.clear(email);
    await userEvent.type(email, ' mom@x.kr ');
    await userEvent.click(screen.getByRole('button', { name: '동의 요청 보내기' }));

    expect(await screen.findByText('mom@x.kr 로 동의 요청 메일을 보냈습니다.')).toBeInTheDocument();
    expect(sent(seen, `${GUARDIAN}/request`)).toEqual([{ guardian_email: 'mom@x.kr' }]);
    expect(screen.getByText(/보호자의 동의를 기다리는 중입니다/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '다시 보내기' })).toBeInTheDocument();
  });

  it('보호자가 이미 동의했다는 답이면 까닭을 적고 내 정보를 다시 읽어 창을 거둔다', async () => {
    const { seen } = minor(() => json(409, { detail: 'x', code: 'guardian_consent_active' }), 'revoked', 'consented');
    renderApp('/me/guardian');

    expect(await screen.findByText(/보호자가 동의를 철회해 충전할 수 없습니다/)).toBeInTheDocument();
    const reads = count(seen, '/api/v1/auth/me');
    await userEvent.type(screen.getByLabelText('보호자의 이메일'), 'dad@x.kr');
    await userEvent.click(screen.getByRole('button', { name: '동의 요청 보내기' }));

    await vi.waitFor(() => expect(count(seen, '/api/v1/auth/me')).toBeGreaterThan(reads));
    expect(await screen.findByText(/보호자가 동의했습니다/)).toBeInTheDocument();
    expect(screen.queryByLabelText('보호자의 이메일')).toBeNull();
  });

  it('칸의 글은 칸에, 너무 자주면 기다릴 초를 적는다', async () => {
    let answer = json(400, { guardian_email: ['보호자의 이메일을 적어 주세요. 내 이메일은 쓸 수 없습니다.'] });
    minor(() => answer);
    renderApp('/me/guardian');

    await userEvent.type(await screen.findByLabelText('보호자의 이메일'), 'other@x.kr');
    await userEvent.click(screen.getByRole('button', { name: '동의 요청 보내기' }));
    expect(await screen.findByText('보호자의 이메일을 적어 주세요. 내 이메일은 쓸 수 없습니다.')).toBeInTheDocument();
    answer = json(429, { detail: 'x', code: 'guardian_request_unavailable', retry_after: 40 });
    await userEvent.click(screen.getByRole('button', { name: '동의 요청 보내기' }));
    expect(await screen.findByText(/40초 뒤에 다시 해 주세요/)).toBeInTheDocument();
  });

  it('본인인증 전이면 본인인증으로, 성년이면 필요 없다고 알린다', async () => {
    minor(() => json(202, {}), 'none', 'none', { verified: false, legal_adult: false, adult_content: false });
    renderApp('/me/guardian');
    expect(await screen.findByRole('link', { name: '본인인증하기' })).toHaveAttribute('href', '/me/identity');
    expect(screen.queryByLabelText('보호자의 이메일')).toBeNull();
  });
});

describe('보호자의 링크', () => {
  it('로그인 없이 링크를 열고, 성년 전이면 막고, 성인 보호자로 인증하면 동의한다', async () => {
    let answer = json(403, { detail: 'x', code: 'guardian_not_adult' });
    const { seen } = guardian({ [`POST ${GUARDIAN}/consent`]: () => answer });
    renderApp('/guardian/consent#token=c-1');

    await userEvent.click(await screen.findByRole('button', { name: '성년 전(만 18세, 막힘)' }));
    await userEvent.click(screen.getByRole('button', { name: '이 사람으로 동의하기' }));
    expect(await screen.findByText(/보호자 본인의 휴대폰으로 인증해 주세요/)).toBeInTheDocument();

    answer = json(200, { detail: '동의를 적었습니다.' });
    await userEvent.click(screen.getByRole('button', { name: '성인 보호자(만 45세)' }));
    await userEvent.click(screen.getByRole('button', { name: '이 사람으로 동의하기' }));
    expect(await screen.findByRole('heading', { name: '동의했습니다' })).toBeInTheDocument();
    expect(sent(seen, `${GUARDIAN}/consent`)[1]).toEqual({ consent_token: 'c-1', identity_token: fakeIdentityToken(GUARDIAN_FAKE_DI, birthDateForAge(koreanToday(), 45)) });
  });

  it('쓸 수 없는 링크면 까닭을 적고 창을 거둔다. 글자가 없는 링크는 열지 않는다', async () => {
    guardian({ [`POST ${GUARDIAN}/consent`]: () => json(400, { detail: 'x', code: 'guardian_link_invalid' }) });
    const { unmount } = renderApp('/guardian/consent#token=old');
    await userEvent.click(await screen.findByRole('button', { name: '이 사람으로 동의하기' }));
    expect(await screen.findByText(LINK_INVALID)).toBeInTheDocument();
    expect(screen.queryByRole('form', { name: '시험용 본인확인' })).toBeNull();
    unmount();

    renderApp('/guardian/consent');
    expect(await screen.findByText(/링크가 올바르지 않습니다/)).toBeInTheDocument();
  });

  it('철회는 단추로 낸다. 이미 철회한 링크면 그렇다고 적는다', async () => {
    let revoked = true;
    const { seen } = guardian({ [`POST ${GUARDIAN}/revoke`]: () => json(200, { detail: '철회했다', revoked }) });
    const { unmount } = renderApp('/guardian/revoke#token=r-1');

    await userEvent.click(await screen.findByRole('button', { name: '동의 철회하기' }));
    expect(await screen.findByRole('heading', { name: '동의를 철회했습니다' })).toBeInTheDocument();
    expect(sent(seen, `${GUARDIAN}/revoke`)).toEqual([{ revoke_token: 'r-1' }]);
    unmount();

    revoked = false;
    renderApp('/guardian/revoke#token=r-1');
    await userEvent.click(await screen.findByRole('button', { name: '동의 철회하기' }));
    expect(await screen.findByRole('heading', { name: '이미 철회한 동의입니다' })).toBeInTheDocument();
  });
});

describe('보호자 동의의 순수한 함수', () => {
  it('링크, 단계, 부탁할 수 있는지, 이메일, 막지 않는 경로', () => {
    expect(parseGuardianLink('#token=a%2Bb')).toBe('a+b');
    expect(parseGuardianLink('#x=1')).toBeNull();
    expect(guardianStage(me({ verified: false, legal_adult: false, adult_content: false }, 'none'))).toBe('unverified');
    expect(guardianStage(me(ADULT, 'consented'))).toBe('adult');
    expect(guardianStage(me(MINOR, 'requested'))).toBe('requested');
    expect(canRequest('consented')).toBe(false);
    expect(canRequest('revoked')).toBe(true);
    expect(guardianEmailHint('', 'me@x.kr')).toBeNull();
    expect(guardianEmailHint('mom@x', 'me@x.kr')).toContain('확인');
    expect(guardianEmailHint('mom@x.kr', 'me@x.kr')).toBeNull();
    expect(isAuthPath('/guardian/consent')).toBe(true);
  });

  it('실패: 요청은 내 정보를 다시 읽을지, 동의는 링크를 더 쓸 수 있는지', () => {
    expect(describeRequestProblem(new ApiError({ status: 409, detail: 'x', code: 'guardian_not_needed' })).reread).toBe(true);
    expect(describeRequestProblem(new ApiError({ status: 400, detail: 'x', fields: { guardian_email: ['틀림'] } })).email).toBe('틀림');
    expect(describeConsentProblem(new ApiError({ status: 409, detail: 'x', code: 'guardian_is_minor' })).restart).toBe(false);
    expect(describeConsentProblem(new ApiError({ status: 409, detail: 'x', code: 'guardian_not_needed' })).restart).toBe(true);
    expect(describeConsentProblem(new ApiError({ status: 503, detail: 'x' })).message).toContain('지금은 본인인증을');
  });
});
