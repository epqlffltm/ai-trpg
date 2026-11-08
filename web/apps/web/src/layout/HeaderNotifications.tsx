// web/apps/web/src/layout/HeaderNotifications.tsx
// 위쪽 줄의 알림 종(A10, Stitch 설계서의 [모든 화면의 틀]). 읽지 않은 수를 붙이고, 누르면 아래로 알림 창이 펼쳐진다(NotificationPanel).
// 로그인했을 때만 둔다(AppHeader). 수는 1분마다 묻는다(notificationQueries.ts). 읽지 못했으면 수 없이 "알림"만 보인다.
// 넓은 화면은 "알림" 글자, 좁은 화면은 종 아이콘이다(설계서의 모바일 한 줄. 글자와 아이콘 가운데 하나를 app.css 가 숨긴다).

import { useQuery } from '@tanstack/react-query';
import { unreadCountQuery } from '../pages/notifications/notificationQueries';
import { badgeText } from '../pages/notifications/notificationText';
import { NotificationPanel } from './NotificationPanel';
import { usePopover } from './usePopover';

export function HeaderNotifications() {
  const unread = useQuery(unreadCountQuery());
  const { open, toggle, close, ref } = usePopover();
  const count = unread.data?.unread ?? 0;
  const badge = badgeText(count);
  return (
    <div className="header-popover" ref={ref}>
      <button
        type="button"
        className="app-header__notifications"
        aria-expanded={open}
        aria-label={count > 0 ? `알림, 읽지 않은 것 ${count}개` : '알림'}
        onClick={toggle}
      >
        <svg className="app-header__icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
          <path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4zM10 20a2 2 0 0 0 4 0" />
        </svg>
        <span className="app-header__label">알림</span>
        {badge ? (
          <span className="app-header__badge" aria-hidden="true">
            {badge}
          </span>
        ) : null}
      </button>
      {open ? <NotificationPanel unread={count} onClose={close} /> : null}
    </div>
  );
}
