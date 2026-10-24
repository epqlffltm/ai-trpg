// web/apps/web/src/pages/notifications/notificationQueries.ts
// 알림함(A10)이 읽는 것의 열쇠와 부르는 함수. 머리의 알림 표시와 알림 화면이 함께 쓴다.
// 읽지 않은 수는 1분마다 묻는다(알림 서버에 스트림이 없다, #525). 창이 뒤에 있으면 묻지 않고, 창에 돌아오면 바로 묻는다.
// 열쇠의 앞(NOTIFICATION_KEY)을 무르면 수와 목록이 함께 다시 읽힌다.

import { infiniteQueryOptions, queryOptions } from '@tanstack/react-query';
import { fetchMutes, fetchNotifications, fetchUnreadCount } from '../../api/notifications';

export const NOTIFICATION_KEY = ['notification'] as const;

/** 읽지 않은 수를 묻는 간격 */
export const UNREAD_POLL_MS = 60 * 1000;

export function unreadCountQuery() {
  return queryOptions({
    queryKey: [...NOTIFICATION_KEY, 'unread'],
    queryFn: ({ signal }) => fetchUnreadCount(signal),
    refetchInterval: UNREAD_POLL_MS,
    refetchOnWindowFocus: true,
    staleTime: 15 * 1000,
  });
}

/** 알림. 최근 것부터 한 쪽씩. 다음 쪽은 앞 쪽의 next_before 로 읽고, null 이면 끝이다 */
export function notificationsQuery() {
  return infiniteQueryOptions({
    queryKey: [...NOTIFICATION_KEY, 'list'],
    queryFn: ({ pageParam, signal }) => fetchNotifications(pageParam, signal),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (lastPage) => lastPage.next_before ?? undefined,
  });
}

export function mutesQuery() {
  return queryOptions({
    queryKey: [...NOTIFICATION_KEY, 'mutes'],
    queryFn: ({ signal }) => fetchMutes(signal),
  });
}
