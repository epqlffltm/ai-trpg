// web/apps/web/src/pages/notifications/NotificationIcon.tsx
// 알림 한 줄의 종류 아이콘(Stitch 9번). 글이 뜻을 다 말하므로 아이콘은 꾸밈이다(읽는 프로그램에는 숨긴다).
// 종류는 source 와 kind 로 고른다(notificationGroup). 모르는 짝은 종 모양이다.

import type { AppNotification } from '../../api/types';

export type NotificationGroup = 'table' | 'wallet' | 'board' | 'follow' | 'operator' | 'other';

/** 운영자의 조치와 신고 처리. 테이블·지갑보다 먼저 본다 */
const OPERATOR_KINDS = new Set(['scenario.sanctioned', 'publishing.banned', 'publishing.unbanned', 'character.hidden', 'character.unhidden']);

/** 알림이 어느 종류의 아이콘을 쓰는가 */
export function notificationGroup(notification: Pick<AppNotification, 'source' | 'kind'>): NotificationGroup {
  const { source, kind } = notification;
  if (OPERATOR_KINDS.has(kind) || kind.endsWith('_report.handled')) return 'operator';
  if (kind.endsWith('.published')) return 'follow';
  if (source === 'billing') return 'wallet';
  if (source === 'board') return 'board';
  if (source === 'game') return 'table';
  return 'other';
}

/** 아이콘마다의 선. 24 칸 격자, 선 굵기는 CSS 가 정한다 */
const PATHS: Record<NotificationGroup, string> = {
  table: 'M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM8.5 8.5h.01M15.5 8.5h.01M12 12h.01M8.5 15.5h.01M15.5 15.5h.01',
  wallet: 'M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18zM12 7v10M9.5 9.5h4a1.5 1.5 0 0 1 0 3h-3a1.5 1.5 0 0 0 0 3h4',
  board: 'M6 3h9l3 3v15H6zM9 9h6M9 13h6M9 17h4',
  follow: 'M4 20l4-1L19 8l-3-3L5 16zM14 7l3 3',
  operator: 'M12 3l7 3v5c0 5-3 8-7 10c-4-2-7-5-7-10V6zM9 12l2 2l4-4',
  other: 'M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0',
};

export function NotificationIcon({ group }: { group: NotificationGroup }) {
  return (
    <span className={`notification__icon notification__icon--${group}`} aria-hidden="true">
      <svg viewBox="0 0 24 24" width="20" height="20" focusable="false">
        <path d={PATHS[group]} />
      </svg>
    </span>
  );
}
