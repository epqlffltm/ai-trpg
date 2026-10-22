// web/apps/web/src/auth/accountProblems.test.ts
// 계정 화면의 실패와 상태의 글이 화면 명세대로인지 본다. 순수한 함수만 부른다.

import { describe, expect, it } from 'vitest';
import { ApiError, NetworkError } from '../api/errors';
import { guardianLabel, identityLabel, showsGuardian } from '../pages/me/accountLabels';
import { allChecked, pendingItems } from '../pages/limited/reconsent';
import { describeAccountProblem, describeConsentProblem, describePasswordChangeProblem } from './accountProblem';

function apiError(status: number, extra: Partial<ConstructorParameters<typeof ApiError>[0]> = {}) {
  return new ApiError({ status, detail: '서버의 글', ...extra });
}

describe('describePasswordChangeProblem', () => {
  it('칸마다의 오류를 그 칸에 둔다', () => {
    expect(describePasswordChangeProblem(apiError(400, { fields: { new_password: ['너무 짧다'] } }))).toMatchObject({
      fields: { new_password: '너무 짧다' },
    });
  });

  it('너무 많이 틀리면 기다리게 한다', () => {
    expect(describePasswordChangeProblem(apiError(429, { retryAfter: 30 }))).toMatchObject({ waitSeconds: 30 });
  });
});

describe('describeConsentProblem', () => {
  it('판이 바뀌었으면 다시 읽게 한다', () => {
    expect(describeConsentProblem(apiError(409, { code: 'consent_outdated' }))).toMatchObject({ consentsChanged: true });
  });

  it('필수 항목의 철회는 탈퇴라고 알린다', () => {
    expect(describeConsentProblem(apiError(400, { code: 'consent_required' })).message).toMatch(/탈퇴/);
  });
});

describe('describeAccountProblem', () => {
  it('서버에 닿지 못하면 그렇게 알리고, 모르는 실패에는 요청 번호를 붙인다', () => {
    expect(describeAccountProblem(new NetworkError(new Error('x'))).message).toMatch(/닿지 못했습니다/);
    expect(describeAccountProblem(apiError(500, { requestId: 'r-1' }))).toMatchObject({ requestId: 'r-1' });
  });
});

describe('accountLabels', () => {
  const unverified = { verified: false, legal_adult: false, adult_content: false };

  it('본인인증의 상태를 글로 바꾼다', () => {
    expect(identityLabel(unverified)).toBe('하지 않음');
    expect(identityLabel({ verified: true, legal_adult: false, adult_content: false })).toBe('했음(미성년자)');
    expect(identityLabel({ verified: true, legal_adult: true, adult_content: true })).toMatch(/성인용 내용 열림/);
  });

  it('보호자 동의는 미성년자이거나 기록이 있을 때만 보인다', () => {
    expect(showsGuardian({ identity: unverified, guardian_consent: 'none' })).toBe(false);
    expect(showsGuardian({ identity: { ...unverified, verified: true }, guardian_consent: 'none' })).toBe(true);
    expect(showsGuardian({ identity: unverified, guardian_consent: 'revoked' })).toBe(true);
    expect(guardianLabel('requested')).toMatch(/기다리는 중/);
  });
});

describe('reconsent', () => {
  const state = (item: string, pending: boolean) => ({
    item,
    version: 2,
    required: true,
    pending,
    agreed_version: 1,
    agreed_at: '2026-10-20T00:00:00Z',
  });

  it('pending 인 항목만 받고, 모두 체크해야 보낼 수 있다', () => {
    const items = pendingItems([state('terms', true), state('privacy', false)]);
    expect(items.map((item) => item.item)).toEqual(['terms']);
    expect(allChecked(items, {})).toBe(false);
    expect(allChecked(items, { terms: true })).toBe(true);
    expect(allChecked([], {})).toBe(false);
  });
});
