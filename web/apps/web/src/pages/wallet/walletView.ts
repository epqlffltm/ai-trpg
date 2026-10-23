// web/apps/web/src/pages/wallet/walletView.ts
// 지갑(A6)이 보일 글. 순수한 함수다. 값은 모두 결제 서버가 준 것이고 양은 글자다("80"). 화면이 더하거나 빼지 않는다.
// 산 크레딧은 골드(paid), 무료 크레딧은 실버(free)라 부른다(docs/product/screens.md 의 A6).
// 판 안의 돈(은화 같은 것, room/money.ts)과 다르다. 이것은 서술 값을 내는 크레딧이다.

import type { TableEvent, Wallet, WalletEntry } from '../../api/types';

const KINDS: Record<WalletEntry['kind'], string> = { paid: '골드', free: '실버' };

/** 원장 줄의 말. hold 는 그 홀드의 지금 상태로 가른다 */
const REASONS: Record<Exclude<WalletEntry['reason'], 'hold'>, string> = {
  deposit: '충전',
  grant: '지급',
  spend: '사용',
  release: '서술 값 반환',
  expire: '만료',
  refund: '환불',
  unrefund: '환불 취소',
  forfeit: '탈퇴로 소멸',
  regroup: '정리',
};

const HOLDS: Record<NonNullable<WalletEntry['hold_status']>, string> = {
  held: '서술 값 대기',
  captured: '서술 값 사용',
  released: '서술 값(반환됨)',
};

const DAY_MS = 24 * 60 * 60 * 1000;
const HOUR_MS = 60 * 60 * 1000;

export function kindLabel(kind: WalletEntry['kind']): string {
  return KINDS[kind];
}

/** 원장 한 줄의 말. "충전", "서술 값 대기" … */
export function entryLabel(entry: WalletEntry): string {
  if (entry.reason !== 'hold') return REASONS[entry.reason];
  return entry.hold_status ? HOLDS[entry.hold_status] : '서술 값';
}

/** 보일 줄. 내부 정리(regroup)는 같은 작업의 줄을 더하면 0 이라 숨긴다 */
export function visibleEntries(entries: WalletEntry[]): WalletEntry[] {
  return entries.filter((entry) => entry.reason !== 'regroup');
}

/** "+80", "-3". 서버의 글에 부호만 붙인다(이미 음수면 그대로) */
export function signedAmount(amount: string): string {
  return amount.startsWith('-') || amount === '0' ? amount : `+${amount}`;
}

/** 줄의 늘고 줆. 화면의 색을 가른다 */
export function entryDirection(entry: WalletEntry): 'in' | 'out' {
  return entry.amount.startsWith('-') ? 'out' : 'in';
}

/** "3일 뒤", "5시간 뒤", "곧". 이미 지났으면 "곧"(서버가 다시 읽으면 빠진다) */
export function timeUntil(iso: string, now: number): string {
  const left = new Date(iso).getTime() - now;
  if (Number.isNaN(left) || left < HOUR_MS) return '곧';
  if (left < DAY_MS) return `${Math.floor(left / HOUR_MS)}시간 뒤`;
  return `${Math.floor(left / DAY_MS)}일 뒤`;
}

/** "실버 10 · 3일 뒤 사라짐". 사라질 실버가 없으면 null. 숫자 뒤의 조사를 고르지 않게 이 꼴로 쓴다 */
export function expiryText(wallet: Wallet, now: number): string | null {
  const next = wallet.next_expiry;
  if (!next) return null;
  return `실버 ${next.amount} · ${timeUntil(next.expires_at, now)} 사라짐`;
}

/** 머리의 짧은 잔액. "골드 80 · 실버 10" */
export function balanceShort(wallet: Wallet): string {
  return `골드 ${wallet.paid} · 실버 ${wallet.free}`;
}

/**
 * 크레딧을 바꿀 수 있는 테이블의 일. 이것이 오면 잔액을 다시 읽는다.
 * 라운드를 닫으면 서술 값을 걸고(hold), 서술이 끝나 다음 라운드가 열리면 잡고(capture), 그만두거나 돌려주면 푼다(release).
 * 모자라다는 알림 뒤에는 충전했는지 볼 수 있게 읽는다.
 */
export const WALLET_EVENTS: ReadonlySet<TableEvent['type']> = new Set<TableEvent['type']>([
  'round_closed',
  'round_opened',
  'narration_credits_short',
  'narration_credits_released',
  'narration_abandoned',
  'table_ended',
]);

export function changesWallet(type: TableEvent['type']): boolean {
  return WALLET_EVENTS.has(type);
}
