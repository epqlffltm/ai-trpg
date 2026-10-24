// web/apps/web/src/layout/HeaderNotifications.tsx
// 머리의 "알림"(A10). 읽지 않은 수를 붙여 알림 화면으로 잇는다. 로그인했을 때만 둔다(AppHeader).
// 수는 1분마다 묻는다(notificationQueries.ts). 읽지 못했으면 수 없이 "알림"만 보인다. 머리 때문에 화면이 깨지지 않게.

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router';
import { unreadCountQuery } from '../pages/notifications/notificationQueries';
import { badgeText } from '../pages/notifications/notificationText';

export function HeaderNotifications() {
  const unread = useQuery(unreadCountQuery());
  const count = unread.data?.unread ?? 0;
  const badge = badgeText(count);
  return (
    <Link to="/notifications" className="app-header__notifications" aria-label={count > 0 ? `알림, 읽지 않은 것 ${count}개` : '알림'}>
      알림
      {badge ? (
        <span className="app-header__badge" aria-hidden="true">
          {badge}
        </span>
      ) : null}
    </Link>
  );
}
