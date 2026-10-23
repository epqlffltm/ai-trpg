// web/apps/web/src/pages/wallet/walletPure.test.ts
// 지갑(A6)의 순수한 함수. 원장 줄의 말, 숨길 줄, 양의 부호, 곧 사라질 실버, 머리의 잔액, 다시 읽을 이벤트, 실패의 글을 본다.

import { describe, expect, it } from 'vitest';
import { ApiError, NetworkError } from '../../api/errors';
import type { Wallet, WalletEntry } from '../../api/types';
import { walletProblemText } from './walletProblem';
import { balanceShort, changesWallet, entryDirection, entryLabel, expiryText, signedAmount, timeUntil, visibleEntries } from './walletView';

const NOW = Date.parse('2026-10-23T00:00:00Z');

function entry(reason: WalletEntry['reason'], extra: Partial<WalletEntry> = {}): WalletEntry {
  return {
    id: '1',
    operation_id: '00000000-0000-4000-8000-000000000001',
    kind: 'free',
    reason,
    amount: '10',
    order_id: null,
    hold_id: null,
    hold_status: null,
    created_at: '2026-10-22T00:00:00Z',
    ...extra,
  };
}

const WALLET: Wallet = { paid: '80', free: '10', total: '90', next_expiry: { amount: '10', expires_at: '2026-10-26T06:00:00Z' } };

describe('원장의 줄', () => {
  it('까닭마다 말이 있고, 서술 값은 홀드의 지금 상태로 가른다', () => {
    expect(entryLabel(entry('deposit'))).toBe('충전');
    expect(entryLabel(entry('forfeit'))).toBe('탈퇴로 소멸');
    expect(entryLabel(entry('hold', { hold_status: 'held' }))).toBe('서술 값 대기');
    expect(entryLabel(entry('hold', { hold_status: 'captured' }))).toBe('서술 값 사용');
    expect(entryLabel(entry('hold', { hold_status: 'released' }))).toBe('서술 값(반환됨)');
    expect(entryLabel(entry('release'))).toBe('서술 값 반환');
  });

  it('내부 정리는 숨기고, 양에는 부호를 붙인다', () => {
    expect(visibleEntries([entry('grant'), entry('regroup'), entry('spend')]).map((one) => one.reason)).toEqual(['grant', 'spend']);
    expect(signedAmount('80')).toBe('+80');
    expect(signedAmount('-3')).toBe('-3');
    expect(signedAmount('0')).toBe('0');
    expect(entryDirection(entry('spend', { amount: '-3' }))).toBe('out');
  });
});

describe('잔액', () => {
  it('곧 사라질 실버는 남은 날, 하루 안이면 남은 시간', () => {
    expect(timeUntil('2026-10-26T06:00:00Z', NOW)).toBe('3일 뒤');
    expect(timeUntil('2026-10-23T05:30:00Z', NOW)).toBe('5시간 뒤');
    expect(timeUntil('2026-10-23T00:10:00Z', NOW)).toBe('곧');
    expect(expiryText(WALLET, NOW)).toBe('실버 10 · 3일 뒤 사라짐');
    expect(expiryText({ ...WALLET, next_expiry: null }, NOW)).toBeNull();
  });

  it('머리의 잔액은 서버의 글 그대로', () => {
    expect(balanceShort(WALLET)).toBe('골드 80 · 실버 10');
  });

  it('서술 값이 걸리거나 잡히거나 풀리는 일이면 다시 읽는다', () => {
    expect(changesWallet('round_opened')).toBe(true);
    expect(changesWallet('narration_credits_short')).toBe(true);
    expect(changesWallet('hp_changed')).toBe(false);
  });

  it('503 은 기다릴 초를 알리고, 닿지 못하면 연결을 보라고 한다', () => {
    expect(walletProblemText(new ApiError({ status: 503, detail: 'x', retryAfter: 5 }))).toBe('결제 서버가 지금 답하지 못합니다. 5초 뒤에 다시 시도하세요.');
    expect(walletProblemText(new NetworkError(new Error('x')))).toContain('연결');
    expect(walletProblemText(new ApiError({ status: 500, detail: 'x' }))).toContain('불러오지 못했습니다');
  });
});
