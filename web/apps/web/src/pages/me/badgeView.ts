// web/apps/web/src/pages/me/badgeView.ts
// 활동 배지(#193)를 보이는 데 쓰는 순수한 함수들. 화면을 그리지 않는다.

import type { Badge } from '../../api/badges';
import { formatDate } from '../../format/dateTime';

/** 받은 수의 한 줄 */
export function earnedLine(earned: number, total: number): string {
  return `받은 배지 ${earned} / ${total}개`;
}

/** 배지 한 칸의 아래 줄. 받았으면 받은 날, 아직이면 "아직" */
export function badgeStatus(badge: Badge): string {
  return badge.earned_at ? `${formatDate(badge.earned_at)}에 받음` : '아직 받지 않음';
}
