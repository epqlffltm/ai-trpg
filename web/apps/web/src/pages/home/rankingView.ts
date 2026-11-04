// web/apps/web/src/pages/home/rankingView.ts
// 이번 주 인기(#985)의 카드에 붙이는 표시. 순위와 최근 7일에 시작한 수다. DOM 을 모르는 순수한 함수다.

import { compactCount } from '../../format/count';

export function rankBadges(rank: number, starts: number): string[] {
  return [`${rank}위`, `이번 주 ${compactCount(starts)}회`];
}
