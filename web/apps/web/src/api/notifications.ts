// web/apps/web/src/api/notifications.ts
// 내 알림함(알림 서버, A10, #385). 다른 서버가 넣은 알림을 읽고 읽음으로 하고, 종류마다 끈다.
// 알림의 문구는 서버가 주지 않는다. 화면이 source 와 kind 로 문장을 만든다(pages/notifications/notificationText.ts).
// 남의 알림 번호는 404(없는 것과 같다). 503 은 공개키를 구할 수 없을 때다(Retry-After). 로그아웃시키지 않는다.

import { apiRequest } from './http';
import type { AppNotification, MuteSettings, NotificationPage, ReadAllResult, UnreadCount } from './types';

const BOX = '/api/v1/notification/me/notifications';

/** 한 쪽에 읽는 알림 수(서버는 1~100) */
export const NOTIFICATION_PAGE_SIZE = 20;

/** 알림의 한 쪽. 최근 것부터. before 는 앞 쪽의 next_before(첫 쪽이면 비운다) */
export function fetchNotifications(before: number | undefined, signal?: AbortSignal): Promise<NotificationPage> {
  return apiRequest<NotificationPage>(BOX, { query: { limit: NOTIFICATION_PAGE_SIZE, before }, ...(signal ? { signal } : {}) });
}

export function fetchUnreadCount(signal?: AbortSignal): Promise<UnreadCount> {
  return apiRequest<UnreadCount>(`${BOX}/unread-count`, signal ? { signal } : {});
}

/** 하나를 읽음으로. 처음 읽은 시각이 남고 다시 해도 바뀌지 않는다 */
export function markNotificationRead(id: number): Promise<AppNotification> {
  return apiRequest<AppNotification>(`${BOX}/${id}/read`, { method: 'POST' });
}

/** upTo 번호까지(포함) 읽지 않은 것을 모두 읽음으로. 화면이 받은 가장 새 번호를 보낸다(그 뒤에 들어온 것은 남는다) */
export function markAllNotificationsRead(upTo: number): Promise<ReadAllResult> {
  return apiRequest<ReadAllResult>(`${BOX}/read-all`, { method: 'POST', body: { up_to: upTo } });
}

/** 끌 수 있는 종류마다 껐는지 */
export function fetchMutes(signal?: AbortSignal): Promise<MuteSettings> {
  return apiRequest<MuteSettings>(`${BOX}/mutes`, signal ? { signal } : {});
}

/** 그 종류를 끄거나(muted) 다시 켠다. 답은 바뀐 뒤의 설정 전체다. 끌 수 없는 종류면 422 */
export function setMute(kind: string, muted: boolean): Promise<MuteSettings> {
  return apiRequest<MuteSettings>(`${BOX}/mutes/${encodeURIComponent(kind)}`, { method: muted ? 'PUT' : 'DELETE' });
}
