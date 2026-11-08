// web/apps/web/src/layout/sidebarRecentView.ts
// 왼쪽 메뉴 열의 최근 대화(Stitch 설계서의 [모든 화면의 틀])를 보이기 전의 순수한 함수. 묶음마다의 줄 수와 "14분 전" 같은 때의 글.

import { formatDate } from '../format/dateTime';

/** 묶음마다 보이는 줄의 수(설계서의 "서너 줄") */
export const RECENT_ROWS = 3;

const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

/** 지금에 견준 때. 1분 안은 "방금", 한 시간 안은 "N분 전", 하루 안은 "N시간 전", 이레 안은 "N일 전", 그보다 오래면 날짜. 읽지 못하면 받은 그대로 */
export function relativeTime(iso: string, now: number): string {
  const at = new Date(iso).getTime();
  if (Number.isNaN(at)) return iso;
  const gap = Math.max(0, now - at);
  if (gap < MINUTE) return '방금';
  if (gap < HOUR) return `${Math.floor(gap / MINUTE)}분 전`;
  if (gap < DAY) return `${Math.floor(gap / HOUR)}시간 전`;
  if (gap < 7 * DAY) return `${Math.floor(gap / DAY)}일 전`;
  return formatDate(iso);
}
