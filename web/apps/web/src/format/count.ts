// web/apps/web/src/format/count.ts
// 수를 짧게 쓴다(#985). 카드의 "이번 주 12.3K회" 같은 것이다. 1,000 부터 K, 1,000,000 부터 M 이고 소수는 한 자리다.

const COMPACT = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 });

export function compactCount(count: number): string {
  return COMPACT.format(count);
}
