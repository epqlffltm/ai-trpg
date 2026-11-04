// web/apps/web/src/pages/wallet/autoChargePure.test.ts
// 자동 충전(#980)의 순수한 함수. 입력 칸의 처음 값, 보낼 값의 검사, 시험용 인증 키, 실패의 글.

import { describe, expect, it } from 'vitest';
import { ApiError, NetworkError } from '../../api/errors';
import type { Product } from '../../api/types';
import { describeAutoChargeProblem } from './autoChargeProblem';
import { fakeAuthKey, initialDraft, toSettings, type AutoChargeDraft } from './autoChargeView';

const PRODUCTS = [
  { id: 'credits-1000', name: '크레딧 1,000', price: 1000, credits: '1000' },
  { id: 'credits-5000', name: '크레딧 5,000', price: 5000, credits: '5000' },
] as Product[];

const GOOD: AutoChargeDraft = { enabled: true, threshold: '500', productId: 'credits-5000', monthlyLimit: '30000' };

describe('입력 칸', () => {
  it('적은 적이 없으면 꺼 둔 채 첫 상품이고, 적었으면 그 값이다', () => {
    expect(initialDraft({ settings: null, consecutive_failures: 0, card: null }, PRODUCTS)).toEqual({
      enabled: false,
      threshold: '500',
      productId: 'credits-1000',
      monthlyLimit: '30000',
    });
    const saved = { enabled: true, threshold: '42', product_id: 'credits-5000', monthly_limit: 9000 };
    expect(initialDraft({ settings: saved, consecutive_failures: 2, card: null }, PRODUCTS)).toEqual({
      enabled: true,
      threshold: '42',
      productId: 'credits-5000',
      monthlyLimit: '9000',
    });
  });

  it('맞는 값을 서버의 모양으로 바꾼다. 빈칸은 지운다', () => {
    expect(toSettings({ ...GOOD, threshold: ' 0 ', monthlyLimit: '5000' }, PRODUCTS)).toEqual({
      settings: { enabled: true, threshold: '0', product_id: 'credits-5000', monthly_limit: 5000 },
      problem: null,
    });
  });

  it('틀린 값은 까닭을 준다', () => {
    const problems = [
      { ...GOOD, threshold: '-1' },
      { ...GOOD, threshold: '1.5' },
      { ...GOOD, threshold: '100001' },
      { ...GOOD, productId: 'credits-7' },
      { ...GOOD, monthlyLimit: '0' },
      { ...GOOD, monthlyLimit: '500001' },
      { ...GOOD, monthlyLimit: '4999' },
    ].map((draft) => toSettings(draft, PRODUCTS).problem);

    expect(problems.every((problem) => typeof problem === 'string' && problem.length > 0)).toBe(true);
    expect(toSettings({ ...GOOD, threshold: '100000', monthlyLimit: '500000' }, PRODUCTS).problem).toBeNull();
  });
});

describe('시험용 인증 키', () => {
  it('앞머리와 등록마다 다른 글자, 자동 결제의 표시를 잇는다', () => {
    expect(fakeAuthKey('fake_card_ok_', '', 'a1-b2')).toBe('fake_card_ok_a1b2');
    expect(fakeAuthKey('fake_card_ok_', 'charge_lost', 'a1-b2')).toBe('fake_card_ok_a1b2_charge_lost');
  });
});

describe('실패의 글', () => {
  it('code 마다 글과 갈 길이 있고, 모르는 것은 일반 글이다', () => {
    expect(describeAutoChargeProblem(new ApiError({ status: 403, detail: 'x', code: 'payment.verification_required' })).link).toEqual({
      to: '/me/identity',
      label: '본인인증하기',
    });
    expect(describeAutoChargeProblem(new ApiError({ status: 503, detail: 'x' })).message).toMatch(/지금 답하지 못합니다/);
    expect(describeAutoChargeProblem(new ApiError({ status: 500, detail: 'x' })).message).toMatch(/처리하지 못했습니다/);
    expect(describeAutoChargeProblem(new NetworkError(new Error('x'))).message).toMatch(/닿지 못했습니다/);
  });
});
