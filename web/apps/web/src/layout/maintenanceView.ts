// web/apps/web/src/layout/maintenanceView.ts
// 점검·장애 화면의 순수한 함수. 점검 시간의 한 줄과 장애의 요청 번호.

import type { Maintenance } from '../api/maintenance';
import { ApiError } from '../api/errors';
import { formatDateTime, formatTime } from '../format/dateTime';

/** "2026년 11월 4일 오전 2:00 ~ 오전 4:00" 꼴. 같은 날이면 끝은 시각만. 시간을 모르면 null */
export function maintenanceWindow(maintenance: Pick<Maintenance, 'startsAt' | 'endsAt'>): string | null {
  const { startsAt, endsAt } = maintenance;
  if (!startsAt && !endsAt) return null;
  if (!startsAt) return `${formatDateTime(endsAt as string)}까지`;
  if (!endsAt) return `${formatDateTime(startsAt)}부터`;
  const sameDay = new Date(startsAt).toDateString() === new Date(endsAt).toDateString();
  return `${formatDateTime(startsAt)} ~ ${sameDay ? formatTime(endsAt) : formatDateTime(endsAt)}`;
}

/** 문의할 때 알려 줄 요청 번호. 서버에 닿지도 못했으면 없다 */
export function requestIdOf(error: unknown): string | null {
  return error instanceof ApiError && error.requestId ? error.requestId : null;
}
