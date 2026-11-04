// web/apps/web/src/pages/wallet/autoChargePure.test.ts
// 자동 충전(#980)의 순수한 함수. 입력 칸의 처음 값, 보낼 값의 검사, 시험용 인증 키, 실패의 글.

import { describe, expect, it } from 'vitest';
import { ApiError, NetworkError } from '../../api/errors';
import type { Product } from '../../api/types';
import { describeAutoChargeProblem } from './autoChargeProblem';
import { agreementLines, fakeAuthKey, initialDraft, pausedText, toSettings, type AutoChargeDraft } from './autoChargeView';

const PRODUCTS = [
  { id: 'credits-1000', name: '크레딧 1,000', price: 1000, credits: '1000' },
  { id: 'credits-5000', name: '크레딧 5,000', price: 5000, credits: '5000' },
] as Product[];

const GOOD: AutoChargeDraft = { enabled: true, threshold: '500', productId: 'credits-5000', monthlyLimit: '30000', agreed: true };
const TERMS = { version: 1, agreed_version: null };

describe('입력 칸', () => {
  it('적은 적이 없으면 꺼 둔 채 첫 상품이고, 적었으면 그 값이다', () => {
    expect(initialDraft({ settings: null, consecutive_failures: 0, card: null, terms: TERMS }, PRODUCTS)).toEqual({
      enabled: false,
      threshold: '500',
      productId: 'credits-1000',
      monthlyLimit: '30000',
      agreed: false,
    });
    const saved = { enabled: true, threshold: '42', product_id: 'credits-5000', monthly_limit: 9000 };
    // 전에 동의했어도 동의하는 칸은 비운 채 시작한다
    expect(initialDraft({ settings: saved, consecutive_failures: 2, card: null, terms: { version: 1, agreed_version: 1 } }, PRODUCTS)).toEqual({
      enabled: true,
      threshold: '42',
      productId: 'credits-5000',
      monthlyLimit: '9000',
      agreed: false,
    });
  });

  it('맞는 값을 서버의 모양으로 바꾼다. 빈칸은 지운다', () => {
    expect(toSettings({ ...GOOD, threshold: ' 0 ', monthlyLimit: '5000' }, PRODUCTS, 3)).toEqual({
      settings: { enabled: true, threshold: '0', product_id: 'credits-5000', monthly_limit: 5000, terms_version: 3 },
      problem: null,
    });
  });

  it('켜려면 동의해야 하고 그 판을 보낸다. 끄는 것은 동의가 필요 없고 판을 보내지 않는다', () => {
    expect(toSettings({ ...GOOD, agreed: false }, PRODUCTS, 1)).toEqual({
      settings: null,
      problem: '자동 충전을 켜려면 자동 결제에 동의해 주세요.',
    });
    expect(toSettings({ ...GOOD, enabled: false, agreed: false }, PRODUCTS, 1)).toEqual({
      settings: { enabled: false, threshold: '500', product_id: 'credits-5000', monthly_limit: 30000 },
      problem: null,
    });
  });

  it('동의할 조건은 고른 값을 그대로 적는다. 값이 틀렸으면 없다', () => {
    expect(agreementLines(GOOD, PRODUCTS)).toEqual([
      '골드가 500 아래로 떨어지면 등록한 카드로 크레딧 5,000(5,000원)을 한 번 결제합니다.',
      '한 달(한국 날짜)에 자동으로 결제하는 돈은 30,000원을 넘지 않습니다.',
      '결제할 때마다 알림함과 메일로 알립니다. 세 번 이어서 되지 않으면 자동 충전을 끕니다.',
      '지갑에서 언제든 끄거나 카드를 지울 수 있습니다.',
    ]);
    expect(agreementLines({ ...GOOD, threshold: 'x' }, PRODUCTS)).toBeNull();
    expect(agreementLines({ ...GOOD, productId: 'credits-7' }, PRODUCTS)).toBeNull();
    expect(agreementLines({ ...GOOD, monthlyLimit: '' }, PRODUCTS)).toBeNull();
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
    ].map((draft) => toSettings(draft, PRODUCTS, 1).problem);

    expect(problems.every((problem) => typeof problem === 'string' && problem.length > 0)).toBe(true);
    expect(toSettings({ ...GOOD, threshold: '100000', monthlyLimit: '500000' }, PRODUCTS, 1).problem).toBeNull();
  });
});

describe('동의가 없어 멈춘 것', () => {
  const on = { enabled: true, threshold: '500', product_id: 'credits-1000', monthly_limit: 30000 };

  it('켜 둔 채 지금의 판에 동의하지 않았을 때만 알린다', () => {
    expect(pausedText({ settings: on, consecutive_failures: 0, card: null, terms: { version: 1, agreed_version: 1 } })).toBeNull();
    expect(pausedText({ settings: { ...on, enabled: false }, consecutive_failures: 0, card: null, terms: { version: 2, agreed_version: 1 } })).toBeNull();
    expect(pausedText({ settings: null, consecutive_failures: 0, card: null, terms: { version: 1, agreed_version: null } })).toBeNull();
    expect(pausedText({ settings: on, consecutive_failures: 0, card: null, terms: { version: 2, agreed_version: 1 } })).toMatch(/내용이 바뀌어 자동 충전을 멈췄습니다/);
    expect(pausedText({ settings: on, consecutive_failures: 0, card: null, terms: { version: 1, agreed_version: null } })).toMatch(/동의가 없어 자동 충전을 멈췄습니다/);
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
