// web/apps/web/src/pages/notifications/useReadNotification.ts
// 알림 하나를 읽음으로 한다(누르거나 "읽음"). 이미 읽었으면 부르지 않는다.
// 답(읽은 시각이 적힌 알림)으로 목록의 그 줄을 바꾸고, 읽지 않은 수를 다시 읽는다.
// 실패하면(404: 보관 기간이 지나 지워졌다 등) 목록과 수를 다시 읽는다. 누른 곳으로 가는 것은 막지 않는다.

import { useQueryClient, type InfiniteData } from '@tanstack/react-query';
import { useCallback } from 'react';
import { markNotificationRead } from '../../api/notifications';
import type { AppNotification, NotificationPage } from '../../api/types';
import { NOTIFICATION_KEY, notificationsQuery, unreadCountQuery } from './notificationQueries';

function replaceItem(data: InfiniteData<NotificationPage> | undefined, next: AppNotification) {
  if (!data) return data;
  return { ...data, pages: data.pages.map((page) => ({ ...page, items: page.items.map((item) => (item.id === next.id ? next : item)) })) };
}

export function useReadNotification(): (notification: AppNotification) => void {
  const queryClient = useQueryClient();
  return useCallback(
    (notification: AppNotification) => {
      if (notification.read_at) return;
      markNotificationRead(notification.id)
        .then((next) => {
          queryClient.setQueryData(notificationsQuery().queryKey, (data: InfiniteData<NotificationPage> | undefined) => replaceItem(data, next));
          void queryClient.invalidateQueries({ queryKey: unreadCountQuery().queryKey });
        })
        .catch(() => void queryClient.invalidateQueries({ queryKey: NOTIFICATION_KEY }));
    },
    [queryClient],
  );
}
