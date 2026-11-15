// web/apps/web/src/layout/sidebarRecentView.ts
// 왼쪽 메뉴 열과 내 채팅 화면의 최근 대화를 보이기 전의 순수한 함수.
// TRPG 테이블, 캐릭터 대화, 스토리를 한 목록으로 섞어 최근 것부터 늘어놓고(서비스로 묶지 않는다), 종류는 줄의 칩으로만 보인다.
// "14분 전" 같은 때의 글도 여기서 만든다.

import { formatDate } from '../format/dateTime';

/** 왼쪽 메뉴 열에 보이는 줄의 수 */
export const RECENT_ROWS = 10;

/** 내 채팅 화면에 보이는 줄의 수 */
export const RECENT_PAGE_ROWS = 50;

/** 줄의 종류. 화면에는 칩의 글(RECENT_KIND_LABELS)로 보인다 */
export type RecentKind = 'trpg' | 'character' | 'story';

export const RECENT_KIND_LABELS: Record<RecentKind, string> = { trpg: 'TRPG', character: '캐릭터', story: '스토리' };

/** 최근 대화의 한 줄. at 은 차례를 정하는 때(테이블은 만든 때, 대화와 스토리는 마지막으로 바뀐 때) */
export type RecentRow = { id: string; kind: RecentKind; to: string; name: string; detail: string; at: string };

/** 종류마다 읽은 줄들을 한 목록으로 섞어, 때가 늦은 것부터 limit 줄. 때를 읽지 못한 줄은 맨 뒤 */
export function mergeRecent(groups: RecentRow[][], limit: number): RecentRow[] {
  const rows = groups.flat();
  rows.sort((left, right) => timeOf(right.at) - timeOf(left.at));
  return rows.slice(0, limit);
}

function timeOf(iso: string): number {
  const at = new Date(iso).getTime();
  return Number.isNaN(at) ? Number.NEGATIVE_INFINITY : at;
}

/** 고른 종류의 줄만. kind 가 null 이면 모두 */
export function filterRecent(rows: RecentRow[], kind: RecentKind | null, search: string): RecentRow[] {
  const needle = search.trim().toLowerCase();
  return rows.filter(
    (row) =>
      (kind === null || row.kind === kind) &&
      (needle === '' || row.name.toLowerCase().includes(needle) || row.detail.toLowerCase().includes(needle)),
  );
}

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
