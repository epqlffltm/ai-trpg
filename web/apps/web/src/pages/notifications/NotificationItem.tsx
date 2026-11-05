// web/apps/web/src/pages/notifications/NotificationItem.tsx
// 알림 한 줄(Stitch 9번). 앞에 읽지 않음의 점과 종류 아이콘, 글(갈 곳이 있으면 그 화면으로 가는 길)과 받은 때.
// 읽지 않았으면 글이 굵고 "읽음" 단추가 있다. 점은 꾸밈이라 읽는 프로그램에는 "새 알림"으로 알린다.
// 길을 누르면 읽음으로 하고 그 화면으로 간다(읽음을 기다리지 않는다). 위쪽 줄의 알림 창도 이 줄을 쓴다.

import { Button } from '@ai-trpg/ui';
import { Link } from 'react-router';
import type { AppNotification } from '../../api/types';
import { formatDateTime } from '../../format/dateTime';
import { NotificationIcon, notificationGroup } from './NotificationIcon';
import type { NotificationLine } from './notificationText';

type Props = { notification: AppNotification; line: NotificationLine; onRead: (notification: AppNotification) => void };

export function NotificationItem({ notification, line, onRead }: Props) {
  const unread = notification.read_at === null;
  return (
    <li className={unread ? 'notification notification--unread' : 'notification'}>
      <span className="notification__dot" aria-hidden="true" />
      <NotificationIcon group={notificationGroup(notification)} />
      <div className="notification__body">
        {unread ? <span className="visually-hidden">새 알림</span> : null}
        {line.to ? (
          <Link className="notification__text" to={line.to} onClick={() => onRead(notification)}>
            {line.text}
          </Link>
        ) : (
          <span className="notification__text">{line.text}</span>
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
