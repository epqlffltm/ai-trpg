// web/apps/web/src/pages/notifications/NotificationItem.tsx
// 알림 한 줄. 글(갈 곳이 있으면 그 화면으로 가는 길)과 받은 때. 읽지 않았으면 "새 알림" 표와 "읽음" 단추.
// 길을 누르면 읽음으로 하고 그 화면으로 간다(읽음을 기다리지 않는다).

import { Button } from '@ai-trpg/ui';
import { Link } from 'react-router';
import type { AppNotification } from '../../api/types';
import { formatDateTime } from '../../format/dateTime';
import type { NotificationLine } from './notificationText';

type Props = { notification: AppNotification; line: NotificationLine; onRead: (notification: AppNotification) => void };

export function NotificationItem({ notification, line, onRead }: Props) {
  const unread = notification.read_at === null;
  return (
    <li className={unread ? 'notification notification--unread' : 'notification'}>
      <div className="notification__body">
        {unread ? <span className="notification__new">새 알림</span> : null}
        {line.to ? (
          <Link to={line.to} onClick={() => onRead(notification)}>
            {line.text}
          </Link>
        ) : (
          <span>{line.text}</span>
        )}
        <time className="hint notification__time" dateTime={notification.created_at}>
          {formatDateTime(notification.created_at)}
        </time>
      </div>
      {unread ? (
        <Button variant="quiet" aria-label={`읽음: ${line.text}`} onClick={() => onRead(notification)}>
          읽음
        </Button>
      ) : null}
    </li>
  );
}
